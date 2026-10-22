// Minimal DOM harness for the dashboard's card renderer; run with `node tests/browser_pending_regression.js`.
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');

function node() {
  return {
    className: '', textContent: '', href: '', dataset: {}, attrs: {}, children: [], listeners: {},
    classList: { add(value) { if (!value) throw new Error('empty class token'); }, toggle() {} },
    setAttribute(key, value) { this.attrs[key] = value; },
    addEventListener(key, handler) { this.listeners[key] = handler; },
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = [...items]; },
    querySelector(selector) { return this.parts[selector]; },
  };
}
const list = node(), form = node(), message = node(), refresh = node();
form.querySelector = () => node();
let cards = [];
const template = { content: { cloneNode() {
  const parts = Object.fromEntries(['.card', '.status', '.url', '.meta', '.err', '.delete'].map(key => [key, node()]));
  parts['.card'].parts = parts;
  const fragment = node(); fragment.parts = parts;
  fragment.querySelector = key => parts[key];
  fragment.mount = () => { list.children.push(fragment); cards.push(parts); };
  return fragment;
} } };
list.append = (...items) => { for (const item of items) { if (item.mount) item.mount(); else list.children.push(item); } };
const document = {
  querySelector(selector) { return ({'#list':list,'#add-form':form,'#message':message,'#refresh':refresh,'#card':template})[selector]; },
  createElement() { return node(); },
  createTextNode(text) { return {textContent:text}; },
};
const items = [
  {id:1,url:'https://pending.example',status:'PENDING',http_code:null},
  {id:2,url:'https://up.example',status:'UP',http_code:200,elapsed_ms:8,checked_at:'2026-01-01T00:00:00Z'},
  {id:3,url:'https://down.example',status:'DOWN',http_code:null,elapsed_ms:5,checked_at:'2026-01-01T00:00:01Z',error:'timeout'},
];
const sandbox = {document, fetch: async () => ({ok:true,json:async()=>items}), setInterval(){}, Date, Error, Object, console};
vm.runInNewContext(fs.readFileSync('app/static/app.js','utf8'), sandbox);
setImmediate(() => {
  assert.equal(cards.length, 3);
  assert.equal(cards[0]['.meta'].textContent, 'Pending first check');
  assert.equal(cards[1]['.meta'].textContent.startsWith('UP'), true);
  assert.equal(cards[2]['.meta'].textContent.startsWith('DOWN'), true);
  for (const card of cards) assert.equal(typeof card['.delete'].listeners.click, 'function');
  console.log('dashboard pending/UP/DOWN and delete regression passed');
});
