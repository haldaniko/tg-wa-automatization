const DEFAULT_STATUS_COLUMN_NAME = 'Webhook status';
const DEFAULT_WHATSAPP_STATUS_COLUMN_NAME = 'WhatsApp status';
const DEFAULT_WORKING_HOURS_TIMEZONE = 'Europe/Sofia';
const DEFAULT_WORKING_HOURS_START_HOUR = 8;
const DEFAULT_WORKING_HOURS_END_HOUR = 18;
const WEEKEND_WORKING_HOURS_START_HOUR = 11;
const WEEKEND_WORKING_HOURS_END_HOUR = 21;
const DEFAULT_SEND_INTERVAL_MINUTES = 3;
const LAST_MESSAGE_SENT_AT_PROPERTY = 'LAST_MESSAGE_SENT_AT';

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
    console.log('Another syncNewLeads execution is already running.');
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
  console.log(`syncNewLeads started at ${new Date().toISOString()}`);

  if (!webhookUrl || !webhookSecret) {
    throw new Error('Set WEBHOOK_URL and WEBHOOK_SECRET in Script properties first.');
  }

  if (!isWithinWorkingHours_(props)) {
    console.log(describeWorkingHours_(props));
    return;
  }

  const queueWaitMs = getQueueWaitMs_(props);
  if (queueWaitMs > 0) {
    console.log(`Queue pause active. Next send in about ${Math.ceil(queueWaitMs / 1000)} seconds.`);
    return;
  }

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = sheetName ? ss.getSheetByName(sheetName) : ss.getActiveSheet();
  if (!sheet) {
    throw new Error(`Sheet was not found: ${sheetName}`);
  }

  const lastRow = sheet.getLastRow();
  if (lastRow < startRow) {
    console.log(`No rows to process. lastRow=${lastRow}, startRow=${startRow}.`);
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

  for (let row = startRow; row <= lastRow; row += 1) {
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

    if (telegramPending) {
      console.log(`Sending Telegram webhook for row ${row}.`);
      const result = postLead_(webhookUrl, webhookSecret, payload);
      sheet.getRange(row, statusColumn).setValue(result.statusText);
      markMessageSent_(props);
      console.log(`Telegram result for row ${row}: ${result.statusText}`);
      return;
    }
    if (whatsappPending) {
      console.log(`Sending WhatsApp webhook for row ${row}.`);
      const result = postLead_(whatsappWebhookUrl, webhookSecret, payload);
      sheet.getRange(row, whatsappStatusColumn).setValue(result.statusText);
      markMessageSent_(props);
      console.log(`WhatsApp result for row ${row}: ${result.statusText}`);
      return;
    }
  }

  console.log('No pending leads found. Check that status cells are empty for rows you want to send.');
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
  const window = getWorkingHoursWindow_(props);
  const startHour = window.startHour;
  const endHour = window.endHour;
  const currentHour = Number(Utilities.formatDate(new Date(), window.timezone, 'H'));

  if (startHour === endHour) {
    return true;
  }
  if (startHour < endHour) {
    return currentHour >= startHour && currentHour < endHour;
  }
  return currentHour >= startHour || currentHour < endHour;
}

function describeWorkingHours_(props) {
  const window = getWorkingHoursWindow_(props);
  const currentTime = Utilities.formatDate(new Date(), window.timezone, 'yyyy-MM-dd HH:mm:ss');
  const dayType = window.isWeekend ? 'weekend' : 'weekday';
  return `Outside working hours. Now=${currentTime} ${window.timezone}, ${dayType} window=${window.startHour}:00-${window.endHour}:00.`;
}

function getWorkingHoursWindow_(props) {
  const timezone =
    props.getProperty('WORKING_HOURS_TIMEZONE') || DEFAULT_WORKING_HOURS_TIMEZONE;
  const dayOfWeek = Number(Utilities.formatDate(new Date(), timezone, 'u'));
  const isWeekend = dayOfWeek === 6 || dayOfWeek === 7;
  if (isWeekend) {
    return {
      timezone: timezone,
      isWeekend: true,
      startHour: parseHour_(WEEKEND_WORKING_HOURS_START_HOUR, 11),
      endHour: parseHour_(WEEKEND_WORKING_HOURS_END_HOUR, 21),
    };
  }

  return {
    timezone: timezone,
    isWeekend: false,
    startHour: parseHour_(
      props.getProperty('WORKING_HOURS_START_HOUR'),
      DEFAULT_WORKING_HOURS_START_HOUR
    ),
    endHour: parseHour_(
      props.getProperty('WORKING_HOURS_END_HOUR'),
      DEFAULT_WORKING_HOURS_END_HOUR
    ),
  };
}

function parseHour_(value, fallback) {
  const hour = Number(value || fallback);
  if (!Number.isFinite(hour) || hour < 0 || hour > 23) {
    return fallback;
  }
  return Math.floor(hour);
}

function getQueueWaitMs_(props) {
  const intervalMinutes = parsePositiveNumber_(
    props.getProperty('SEND_INTERVAL_MINUTES'),
    DEFAULT_SEND_INTERVAL_MINUTES
  );
  const lastSentAt = props.getProperty(LAST_MESSAGE_SENT_AT_PROPERTY);
  if (!lastSentAt) {
    return 0;
  }

  const lastSentTime = Date.parse(lastSentAt);
  if (!Number.isFinite(lastSentTime)) {
    return 0;
  }

  const waitMs = intervalMinutes * 60 * 1000 - (Date.now() - lastSentTime);
  return Math.max(0, waitMs);
}

function markMessageSent_(props) {
  props.setProperty(LAST_MESSAGE_SENT_AT_PROPERTY, new Date().toISOString());
}

function parsePositiveNumber_(value, fallback) {
  const number = Number(value || fallback);
  if (!Number.isFinite(number) || number <= 0) {
    return fallback;
  }
  return number;
}
