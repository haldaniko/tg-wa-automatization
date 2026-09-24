const DEFAULT_STATUS_COLUMN_NAME = 'Webhook status';
const DEFAULT_WHATSAPP_STATUS_COLUMN_NAME = 'WhatsApp status';
const DEFAULT_WORKING_HOURS_TIMEZONE = 'Europe/Sofia';
const DEFAULT_WORKING_HOURS_START_HOUR = 8;
const DEFAULT_WORKING_HOURS_END_HOUR = 18;
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

function markExistingRowsSkippedForWhatsApp() {
  const props = PropertiesService.getScriptProperties();
  const sheetName = props.getProperty('SHEET_NAME');
  const telegramStatusColumnName =
    props.getProperty('STATUS_COLUMN_NAME') || DEFAULT_STATUS_COLUMN_NAME;
  const statusColumnName =
    props.getProperty('WHATSAPP_STATUS_COLUMN_NAME') || DEFAULT_WHATSAPP_STATUS_COLUMN_NAME;
  const startRow = Number(props.getProperty('START_ROW') || '2');
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = sheetName ? ss.getSheetByName(sheetName) : ss.getActiveSheet();
  if (!sheet) {
    throw new Error(`Sheet was not found: ${sheetName}`);
  }

  const headers = sheet
    .getRange(1, 1, 1, sheet.getLastColumn())
    .getValues()[0]
    .map(String);
  const statusColumn = ensureStatusColumn_(sheet, headers, statusColumnName);
  const rowCount = sheet.getLastRow() - startRow + 1;
  if (rowCount <= 0) {
    return;
  }

  const range = sheet.getRange(startRow, statusColumn, rowCount, 1);
  const finalLastColumn = sheet.getLastColumn();
  const finalHeaders = sheet
    .getRange(1, 1, 1, finalLastColumn)
    .getValues()[0]
    .map(String);
  const rows = sheet.getRange(startRow, 1, rowCount, finalLastColumn).getValues();
  const marker = `SKIP existing ${new Date().toISOString()}`;
  const currentStatuses = range.getValues();
  const statuses = rows.map((values, rowIndex) => {
    const currentStatus = currentStatuses[rowIndex][0];
    if (String(currentStatus || '').trim()) {
      return [currentStatus];
    }
    const hasLeadData = values.some((value, columnIndex) => {
      const header = finalHeaders[columnIndex];
      return (
        header !== telegramStatusColumnName &&
        header !== statusColumnName &&
        String(value || '').trim()
      );
    });
    return [hasLeadData ? marker : ''];
  });
  range.setValues(statuses);
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
  const whatsappWebhookUrl = props.getProperty('WHATSAPP_WEBHOOK_URL');
  const webhookSecret = props.getProperty('WEBHOOK_SECRET');
  const sheetName = props.getProperty('SHEET_NAME');
  const statusColumnName = props.getProperty('STATUS_COLUMN_NAME') || DEFAULT_STATUS_COLUMN_NAME;
  const whatsappStatusColumnName =
    props.getProperty('WHATSAPP_STATUS_COLUMN_NAME') || DEFAULT_WHATSAPP_STATUS_COLUMN_NAME;
  const startRow = Number(props.getProperty('START_ROW') || '2');

  if (!webhookUrl || !webhookSecret) {
    throw new Error('Set WEBHOOK_URL and WEBHOOK_SECRET in Script properties first.');
  }

  if (!isWithinWorkingHours_(props)) {
    return;
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
  const headersWithTelegramStatus = sheet
    .getRange(1, 1, 1, sheet.getLastColumn())
    .getValues()[0]
    .map(String);
  const whatsappStatusColumn = whatsappWebhookUrl
    ? ensureStatusColumn_(sheet, headersWithTelegramStatus, whatsappStatusColumnName)
    : null;
  const finalLastColumn = sheet.getLastColumn();
  const finalHeaders = sheet.getRange(1, 1, 1, finalLastColumn).getValues()[0].map(String);

  let processed = 0;
  for (let row = startRow; row <= lastRow && processed < MAX_ROWS_PER_RUN; row += 1) {
    const telegramStatus = String(sheet.getRange(row, statusColumn).getValue() || '').trim();
    const whatsappStatus = whatsappStatusColumn
      ? String(sheet.getRange(row, whatsappStatusColumn).getValue() || '').trim()
      : '';
    const telegramPending = !telegramStatus;
    const whatsappPending = Boolean(whatsappWebhookUrl && !whatsappStatus);
    if (!telegramPending && !whatsappPending) {
      continue;
    }

    const values = sheet.getRange(row, 1, 1, finalLastColumn).getValues()[0];
    const lead = {};
    finalHeaders.forEach((header, index) => {
      if (
        header &&
        header !== statusColumnName &&
        header !== whatsappStatusColumnName
      ) {
        lead[header] = values[index];
      }
    });
    if (Object.values(lead).every((value) => String(value || '').trim() === '')) {
      continue;
    }

    const payload = {
      spreadsheetId: ss.getId(),
      spreadsheetName: ss.getName(),
      sheetName: sheet.getName(),
      rowNumber: row,
      headers: finalHeaders,
      values: values,
      lead: lead,
    };

    let rowProcessed = false;
    if (telegramPending) {
      const result = postLead_(webhookUrl, webhookSecret, payload);
      sheet.getRange(row, statusColumn).setValue(result.statusText);
      rowProcessed = true;
    }
    if (whatsappPending) {
      const result = postLead_(whatsappWebhookUrl, webhookSecret, payload);
      sheet.getRange(row, whatsappStatusColumn).setValue(result.statusText);
      rowProcessed = true;
    }
    if (rowProcessed) {
      processed += 1;
    }
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

function isWithinWorkingHours_(props) {
  const timezone =
    props.getProperty('WORKING_HOURS_TIMEZONE') || DEFAULT_WORKING_HOURS_TIMEZONE;
  const startHour = parseHour_(
    props.getProperty('WORKING_HOURS_START_HOUR'),
    DEFAULT_WORKING_HOURS_START_HOUR
  );
  const endHour = parseHour_(
    props.getProperty('WORKING_HOURS_END_HOUR'),
    DEFAULT_WORKING_HOURS_END_HOUR
  );
  const currentHour = Number(Utilities.formatDate(new Date(), timezone, 'H'));

  if (startHour === endHour) {
    return true;
  }
  if (startHour < endHour) {
    return currentHour >= startHour && currentHour < endHour;
  }
  return currentHour >= startHour || currentHour < endHour;
}

function parseHour_(value, fallback) {
  const hour = Number(value || fallback);
  if (!Number.isFinite(hour) || hour < 0 || hour > 23) {
    return fallback;
  }
  return Math.floor(hour);
}
