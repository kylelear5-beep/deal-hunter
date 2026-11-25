/**
 * Deal Hunter menu for the "Deal Hunter Settings Check" Google Sheet.
 * Menu: Run now, Pause, Resume, Refresh, Open site, Open last run log, Setup.
 * The GitHub key is kept in this script's private settings, never in a cell.
 */
var REPO = 'kylelear5-beep/deal-hunter';
var WORKFLOW = 'deal-hunter.yml';
var SITE = 'https://kylelear5-beep.github.io/deal-hunter/';
var STATUS_TAB = 'Settings Check';
var FEEDS = {
  'Settings Check': 'api/status.csv',
  'Stats': 'api/stats.csv',
  'Latest Deals': 'api/deals.csv'
};
var KEY_PAGE = 'https://github.com/settings/personal-access-tokens/new';

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Deal Hunter')
    .addItem('Run now', 'runNow')
    .addItem('Refresh', 'refresh')
    .addSeparator()
    .addItem('Pause automatic runs', 'pause')
    .addItem('Resume automatic runs', 'resume')
    .addSeparator()
    .addItem('Open site', 'openSite')
    .addItem('Open last run log', 'openLastLog')
    .addSeparator()
    .addItem('Setup (GitHub key)', 'setup')
    .addItem('Setup email sign-ups (Brevo key)', 'setupEmail')
    .addToUi();
}

// ---------------------------------------------------------------- setup
function setup() {
  var ui = SpreadsheetApp.getUi();
  var r = ui.prompt('Deal Hunter setup',
    'Paste your GitHub key below (it starts with github_pat_).\n' +
    'Need one? Make it at: ' + KEY_PAGE + '\n' +
    'Repository: deal-hunter only. Permission: Actions = Read and write.',
    ui.ButtonSet.OK_CANCEL);
  if (r.getSelectedButton() !== ui.Button.OK) return;
  var key = r.getResponseText().trim();
  if (!key) return;
  PropertiesService.getScriptProperties().setProperty('GH_KEY', key);
  var test = gh_('get', '/actions/workflows/' + WORKFLOW);
  if (test.code !== 200) {
    PropertiesService.getScriptProperties().deleteProperty('GH_KEY');
    ui.alert('That key did not work (GitHub said ' + test.code + ').\n' +
      'Check it is for the deal-hunter repository with Actions = Read and write.');
    return;
  }
  // Keep the "Last run" line fresh every 30 minutes, even when the Sheet is closed.
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'refresh') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('refresh').timeBased().everyMinutes(30).create();
  refresh();
  ui.alert('Done. The Deal Hunter menu now works.');
}

// ---------------------------------------------------------------- actions
function runNow() {
  if (!needKey_()) return;
  var res = gh_('post', '/actions/workflows/' + WORKFLOW + '/dispatches', { ref: 'main' });
  if (res.code === 204) {
    toast_('Run started. Deals and the site update in about 10 to 15 minutes.');
  } else if (res.code === 403 || res.code === 422) {
    alert_('Automatic runs are paused. Use "Resume automatic runs" first.');
  } else {
    alert_('GitHub said ' + res.code + '. Try again in a minute.');
  }
  writeLastRun_();
}

function pause() {
  if (!needKey_()) return;
  var res = gh_('put', '/actions/workflows/' + WORKFLOW + '/disable');
  toast_(res.code === 204 ? 'Paused. No new runs will start.' : 'GitHub said ' + res.code);
  writeLastRun_();
}

function resume() {
  if (!needKey_()) return;
  var res = gh_('put', '/actions/workflows/' + WORKFLOW + '/enable');
  if (res.code !== 204) { alert_('GitHub said ' + res.code); return; }
  gh_('post', '/actions/workflows/' + WORKFLOW + '/dispatches', { ref: 'main' });
  toast_('Resumed. A run is starting now.');
  writeLastRun_();
}

function refresh() {
  var ss = SpreadsheetApp.getActive();
  var stamp = new Date().getTime();
  Object.keys(FEEDS).forEach(function (tab) {
    var sh = ss.getSheetByName(tab);
    if (!sh) return;
    var cell = findFeedCell_(sh);
    if (cell) cell.setFormula('=IMPORTDATA("' + SITE + FEEDS[tab] + '?sheet=' + stamp + '")');
  });
  keepScheduleAlive_();
  writeLastRun_();
  toast_('Refreshed.');
}

// If the 30-minute chain ever stops (no run for 75+ minutes, nothing waiting, not paused),
// start a run. Runs every 30 minutes with refresh(), even when the Sheet is closed.
function keepScheduleAlive_() {
  if (!key_()) return;
  var wf = gh_('get', '/actions/workflows/' + WORKFLOW);
  if (wf.code !== 200 || wf.json.state !== 'active') return;   // paused on purpose
  var res = gh_('get', '/actions/workflows/' + WORKFLOW + '/runs?per_page=5');
  if (res.code !== 200) return;
  var runs = res.json.workflow_runs || [];
  var busy = runs.some(function (r) { return r.status !== 'completed'; });
  var newest = runs.length ? new Date(runs[0].created_at) : new Date(0);
  if (busy || (new Date() - newest) < 75 * 60000) return;
  var go = gh_('post', '/actions/workflows/' + WORKFLOW + '/dispatches', { ref: 'main' });
  Logger.log('Schedule had stopped; started a run (GitHub said ' + go.code + ')');
}

function openSite() { open_(SITE); }

function openLastLog() {
  var run = lastRun_();
  open_(run ? run.html_url : 'https://github.com/' + REPO + '/actions');
}

// ---------------------------------------------------------------- "Last run" line
function writeLastRun_() {
  var sh = SpreadsheetApp.getActive().getSheetByName(STATUS_TAB);
  if (!sh || !key_()) return;
  var run = lastRun_();
  var wf = gh_('get', '/actions/workflows/' + WORKFLOW);
  var state = wf.code === 200 ? wf.json.state : '';
  var when = '', result = 'No runs found', link = '';
  if (run) {
    var t = new Date(run.run_started_at || run.created_at);
    var mins = Math.round((new Date() - t) / 60000);
    when = Utilities.formatDate(t, 'America/New_York', 'MMM d, h:mm a') +
      ' (' + (mins < 60 ? mins + ' min' : Math.round(mins / 60) + ' hr') + ' ago)';
    result = run.status !== 'completed' ? 'Running now' :
      (run.conclusion === 'success' ? 'Worked' : 'PROBLEM: ' + run.conclusion);
    link = run.html_url;
  }
  sh.getRange('A1:D2').setValues([
    ['Last run', when, result, link],
    ['Automatic runs', state === 'active' ? 'On' : (state ? 'PAUSED' : ''),
     'Menu: Deal Hunter (top bar)', 'Updated ' +
       Utilities.formatDate(new Date(), 'America/New_York', 'MMM d, h:mm a')]
  ]);
}

// ---------------------------------------------------------------- helpers
function lastRun_() {
  var res = gh_('get', '/actions/workflows/' + WORKFLOW + '/runs?per_page=1');
  return res.code === 200 && res.json.workflow_runs.length ? res.json.workflow_runs[0] : null;
}

function findFeedCell_(sh) {
  var formulas = sh.getRange(1, 1, 6, 1).getFormulas();
  for (var i = 0; i < formulas.length; i++) {
    if (formulas[i][0].indexOf('IMPORTDATA') >= 0) return sh.getRange(i + 1, 1);
  }
  return null;
}

function key_() { return PropertiesService.getScriptProperties().getProperty('GH_KEY'); }

function needKey_() {
  if (key_()) return true;
  alert_('First time: choose Deal Hunter > Setup (GitHub key).');
  return false;
}

function gh_(method, path, payload) {
  var opts = {
    method: method, muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + key_(), Accept: 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28' }
  };
  if (payload) { opts.contentType = 'application/json'; opts.payload = JSON.stringify(payload); }
  var resp = UrlFetchApp.fetch('https://api.github.com/repos/' + REPO + path, opts);
  var body = resp.getContentText(), json = null;
  try { json = body ? JSON.parse(body) : null; } catch (e) { json = null; }
  return { code: resp.getResponseCode(), json: json };
}

function open_(url) {
  var html = HtmlService.createHtmlOutput(
    '<p style="font:16px Arial">Opening… <a href="' + url + '" target="_blank">click here if it did not open</a></p>' +
    '<script>window.open(' + JSON.stringify(url) + ',"_blank");google.script.host.close();</script>')
    .setWidth(360).setHeight(80);
  SpreadsheetApp.getUi().showModalDialog(html, 'Deal Hunter');
}

function toast_(msg) { try { SpreadsheetApp.getActive().toast(msg, 'Deal Hunter', 8); } catch (e) {} }
function alert_(msg) { try { SpreadsheetApp.getUi().alert(msg); } catch (e) { Logger.log(msg); } }

// ---------------------------------------------------------------- email sign-ups
// The website's sign-up box posts here (Deploy > Web app). We pass it to Brevo.
// The Brevo key is kept in this script's private settings, never in a cell or on the site.
var BREVO_SIGNUP_LIST = 4;
var CAT_ATTRS = {vintage: 'DEALS_VINTAGE', farm: 'DEALS_FARM', tools: 'DEALS_TOOLS', moto: 'DEALS_MOTO', auto: 'DEALS_AUTO',
  electronics: 'DEALS_TECH', astro: 'DEALS_ASTRO', other: 'DEALS_HOME'};

function setupEmail() {
  var ui = SpreadsheetApp.getUi();
  var r = ui.prompt('Deal Hunter email sign-ups',
    'Paste your Brevo API key below (it starts with xkeysib-).', ui.ButtonSet.OK_CANCEL);
  if (r.getSelectedButton() !== ui.Button.OK) return;
  var m = r.getResponseText().match(/xkeysib-[A-Za-z0-9-]+/);
  if (!m) { ui.alert('That does not look like a Brevo key (it should start with xkeysib-).'); return; }
  PropertiesService.getScriptProperties().setProperty('BREVO_KEY', m[0]);
  var test = UrlFetchApp.fetch('https://api.brevo.com/v3/account',
    {headers: {'api-key': m[0]}, muteHttpExceptions: true});
  if (test.getResponseCode() !== 200) {
    PropertiesService.getScriptProperties().deleteProperty('BREVO_KEY');
    ui.alert('Brevo did not accept that key (' + test.getResponseCode() + '). Try copying it again.');
    return;
  }
  ui.alert('Done. Email sign-ups now go to Brevo.');
}

function signupAttrs_(d) {
  var cats = String(d.cats || '').split(',');
  var a = {DEALS_ALL: cats.indexOf('all') > -1 || !cats.some(function (c) { return CAT_ATTRS[c]; }),
    HAS_PRIME: d.prime === 'yes', LIKES_AUDIOBOOKS: d.audio === 'yes',
    FREQUENCY: d.freq === 'weekly' ? 2 : 1};
  Object.keys(CAT_ATTRS).forEach(function (c) { a[CAT_ATTRS[c]] = cats.indexOf(c) > -1; });
  return a;
}

function doPost(e) {
  var out = function (o) {
    return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
  };
  try {
    var d = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    var email = String(d.email || '').trim().toLowerCase();
    if (d.website) return out({ok: true});                       // bot trap: real people leave it empty
    if (!/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/.test(email) || email.length > 120) return out({ok: false, why: 'email'});
    var key = PropertiesService.getScriptProperties().getProperty('BREVO_KEY');
    if (!key) return out({ok: false, why: 'not set up'});
    var r = UrlFetchApp.fetch('https://api.brevo.com/v3/contacts', {
      method: 'post', contentType: 'application/json', headers: {'api-key': key}, muteHttpExceptions: true,
      payload: JSON.stringify({email: email, attributes: signupAttrs_(d),
        listIds: [BREVO_SIGNUP_LIST], updateEnabled: true})});
    var code = r.getResponseCode();
    logSignup_(email, d, code);
    return out({ok: code < 300, code: code});
  } catch (err) {
    return out({ok: false, why: String(err).slice(0, 100)});
  }
}

// One row per sign-up on the "Sign-ups" tab, newest at the bottom.
var SIGNUP_TAB = 'Sign-ups';
var SHEET_ID = '1sWSb4TBJBCBdyReGPGnTpeVSpbWwTEc4kucJFm6Q1FI';
var CAT_NAMES = {moto: 'Motorcycle parts', auto: 'Car & truck parts', vintage: 'Vintage & classic',
  farm: 'Farm & ranch', tools: 'Tools', electronics: 'Tech', astro: 'Telescope & space', other: 'Home',
  all: 'Everything'};

function logSignup_(email, d, code) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet() || SpreadsheetApp.openById(SHEET_ID);
    var sh = ss.getSheetByName(SIGNUP_TAB);
    if (!sh) {
      sh = ss.insertSheet(SIGNUP_TAB);
      sh.appendRow(['Signed up (NY time)', 'Email', 'Deal types', 'Has Prime', 'Audiobooks',
        'How often', 'Saved in Brevo']);
      sh.getRange(1, 1, 1, 7).setFontWeight('bold').setBackground('#f3f3f3');
      sh.setFrozenRows(1);
    }
    var cats = String(d.cats || '').split(',').filter(String)
      .map(function (c) { return CAT_NAMES[c] || c; }).join(', ') || 'Everything';
    var yn = function (v) { return v === 'yes' ? 'Yes' : v === 'no' ? 'No' : ''; };
    // A leading ' keeps the email as plain text, never a formula.
    sh.appendRow([Utilities.formatDate(new Date(), 'America/New_York', 'yyyy-MM-dd HH:mm'),
      "'" + email, cats, yn(d.prime), yn(d.audio), d.freq === 'weekly' ? 'Weekly' : 'Daily',
      code < 300 ? 'Yes' : 'No (' + code + ')']);
  } catch (err) {
    // Never block a sign-up because the Sheet could not be written.
  }
}
