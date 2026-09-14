const DEFAULT_STATUS_COLUMN_NAME = 'Webhook status';
const MAX_ROWS_PER_RUN = 20;

function installLeadWebhookTriggers() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const triggers = ScriptApp.getUserTriggers(ss);
  triggers.forEach((trigger) => {
    if (trigger.getHandlerFunction() === 'syncNewLeads') {
      ScriptApp.deleteTrigger(trigger);
    }
  });

  ScriptApp.newTrigger('syncNewLeads').forSpreadsheet(ss).onEdit().create();
  ScriptApp.newTrigger('syncNewLeads').forSpreadsheet(ss).onChange().create();
  ScriptApp.newTrigger('syncNewLeads').timeBased().everyMinutes(1).create();
}

function syncNewLeads() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) {
    return;
  }

  try {
    syncNewLeadsLocked_();
  } finally {
    lock.releaseLock();
  }
}

function syncNewLeadsLocked_() {
  const props = PropertiesService.getScriptProperties();
  const webhookUrl = props.getProperty('WEBHOOK_URL');
  const webhookSecret = props.getProperty('WEBHOOK_SECRET');
  const sheetName = props.getProperty('SHEET_NAME');
  const statusColumnName = props.getProperty('STATUS_COLUMN_NAME') || DEFAULT_STATUS_COLUMN_NAME;
  const startRow = Number(props.getProperty('START_ROW') || '2');

  if (!webhookUrl || !webhookSecret) {
    throw new Error('Set WEBHOOK_URL and WEBHOOK_SECRET in Script properties first.');
  }

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = sheetName ? ss.getSheetByName(sheetName) : ss.getActiveSheet();
  if (!sheet) {
    throw new Error(`Sheet was not found: ${sheetName}`);
  }

  const lastRow = sheet.getLastRow();
  if (lastRow < startRow) {
    return;
  }

  const lastColumn = sheet.getLastColumn();
  const headers = sheet.getRange(1, 1, 1, lastColumn).getValues()[0].map(String);
  const statusColumn = ensureStatusColumn_(sheet, headers, statusColumnName);
  const finalLastColumn = sheet.getLastColumn();
  const finalHeaders = sheet.getRange(1, 1, 1, finalLastColumn).getValues()[0].map(String);

  let processed = 0;
  for (let row = startRow; row <= lastRow && processed < MAX_ROWS_PER_RUN; row += 1) {
    const status = String(sheet.getRange(row, statusColumn).getValue() || '').trim();
    if (status) {
      continue;
    }

    const values = sheet.getRange(row, 1, 1, finalLastColumn).getValues()[0];
    if (values.every((value) => String(value || '').trim() === '')) {
      continue;
    }

    const lead = {};
    finalHeaders.forEach((header, index) => {
      if (header && header !== statusColumnName) {
        lead[header] = values[index];
      }
    });

    const payload = {
      spreadsheetId: ss.getId(),
      spreadsheetName: ss.getName(),
      sheetName: sheet.getName(),
      rowNumber: row,
      headers: finalHeaders,
      values: values,
      lead: lead,
    };

    const result = postLead_(webhookUrl, webhookSecret, payload);
    sheet.getRange(row, statusColumn).setValue(result.statusText);
    processed += 1;
  }
}

function postLead_(webhookUrl, webhookSecret, payload) {
  const response = UrlFetchApp.fetch(webhookUrl, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'X-Webhook-Secret': webhookSecret,
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  });

  const code = response.getResponseCode();
  const body = response.getContentText();
  const timestamp = new Date().toISOString();
  const shortBody = body ? body.slice(0, 180).replace(/\s+/g, ' ') : '';

  if (code >= 200 && code < 300) {
    return { ok: true, statusText: `OK ${timestamp} ${shortBody}` };
  }
  return { ok: false, statusText: `ERR ${code} ${timestamp} ${shortBody}` };
}

function ensureStatusColumn_(sheet, headers, statusColumnName) {
  const existingIndex = headers.indexOf(statusColumnName);
  if (existingIndex >= 0) {
    return existingIndex + 1;
  }

  const newColumn = headers.length + 1;
  sheet.getRange(1, newColumn).setValue(statusColumnName);
  return newColumn;
}
