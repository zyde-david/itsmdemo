const http = require('http');
const { WebSocket } = require('ws');

function httpRequest(path, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port: 9222, path, method }, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    });
    req.on('error', reject);
    req.end();
  });
}

class CDPClient {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.events = [];
    ws.on('message', data => {
      const msg = JSON.parse(data.toString());
      if (msg.id !== undefined && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
      } else if (msg.method) {
        this.events.push(msg);
      }
    });
  }
  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this.id;
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error(`CDP timeout: ${method}`));
        }
      }, 10000);
    });
  }
}

function connect(wsUrl) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    ws.on('open', () => resolve(new CDPClient(ws)));
    ws.on('error', reject);
  });
}

async function evalJs(cdp, expression) {
  const res = await cdp.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (res.exceptionDetails) return { exception: res.exceptionDetails.text || res.exceptionDetails.exception?.description };
  return res.result.value;
}

async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const target = JSON.parse(await httpRequest('/json/new?http://127.0.0.1:5000/login', 'PUT'));
  const cdp = await connect(target.webSocketDebuggerUrl);
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Console.enable');
  await wait(1000);
  await evalJs(cdp, `document.querySelector('[name=username]').value='admin'; document.querySelector('[name=password]').value='demo2026'; document.querySelector('form').submit();`);
  await wait(1200);
  const pages = [
    { path: '/tickets', table: '#ticketsTable', header: 1, card: "a[onclick*=\"filterTicketStatus('open')\"]" },
    { path: '/assets', table: '#assetsTable', header: 1, card: "a[onclick*=\"filterAssetStatus('active')\"]" },
    { path: '/staff', table: '#staffTable', header: 1, card: null },
    { path: '/knowledge', table: '#kbTable', header: 1, card: null }
  ];
  const results = [];
  for (const page of pages) {
    cdp.events = [];
    await cdp.send('Page.navigate', { url: 'http://127.0.0.1:5000' + page.path });
    await wait(2200);
    const before = await evalJs(cdp, `(() => {
      const table = document.querySelector('${page.table}');
      const dt = !!(window.jQuery && $.fn.dataTable && $.fn.dataTable.isDataTable('${page.table}'));
      const rows = table ? [...table.querySelectorAll('tbody tr')].slice(0, 5).map(r => r.innerText.replace(/\s+/g,' ').trim()) : [];
      return { url: location.pathname, dt, rows, wrapper: !!document.querySelector('.dataTables_wrapper'), thClasses: table ? [...table.querySelectorAll('thead th')].map(th => th.className) : [] };
    })()`);
    await evalJs(cdp, `document.querySelectorAll('${page.table} thead th')[${page.header}].click()`);
    await wait(700);
    const after = await evalJs(cdp, `(() => {
      const table = document.querySelector('${page.table}');
      return { rows: table ? [...table.querySelectorAll('tbody tr')].slice(0, 5).map(r => r.innerText.replace(/\s+/g,' ').trim()) : [], order: window.jQuery && $('${page.table}').DataTable ? $('${page.table}').DataTable().order() : null };
    })()`);
    let cardResult = null;
    if (page.card) {
      cardResult = await evalJs(cdp, `(() => {
        const beforeCount = $('${page.table}').DataTable().rows({filter:'applied'}).count();
        const card = document.querySelector('${page.card}');
        if (!card) return { found:false, beforeCount };
        card.click();
        const afterCount = $('${page.table}').DataTable().rows({filter:'applied'}).count();
        return { found:true, beforeCount, afterCount };
      })()`);
    }
    const errors = cdp.events.filter(e => e.method === 'Runtime.exceptionThrown' || (e.method === 'Console.messageAdded' && e.params.message.level === 'error')).map(e => e.params?.message?.text || e.params?.exceptionDetails?.text || e.method);
    results.push({ page: page.path, before, after, changed: JSON.stringify(before.rows) !== JSON.stringify(after.rows), cardResult, errors });
  }
  console.log(JSON.stringify(results, null, 2));
  await cdp.ws.close();
}

main().catch(e => { console.error(e); process.exit(1); });
