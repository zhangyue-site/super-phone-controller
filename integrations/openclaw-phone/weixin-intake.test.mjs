import test from 'node:test';
import {mkdtempSync, rmSync, readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import assert from 'node:assert/strict';
import {createWeixinIntake, phonePlan} from './weixin-intake.mjs';

const peer = 'owner-fixture@im.wechat';
const account = 'account-fixture';
const channel = 'openclaw-weixin';
const binding = {channel, sender: peer, conversation: JSON.stringify([account, peer]), device: 'target-fixture'};
function setup({bindings = [binding], submit, journalPath} = {}) {
  let time = 1_900_000_000_000;
  const calls = [];
  const handle = createWeixinIntake({bindings, journalPath, targetDevice: binding.device, deviceLabel: '测试手机',
    submit: async (who, cmd) => {
      calls.push({who, cmd});
      return submit ? submit() : {state:'queued', reply:'任务已入队'};
    }, now: () => time});
  const message = (content, messageId, overrides = {}, context = {}) =>
    handle({channel, isGroup: false, messageId, timestamp: time, content, ...overrides},
      {channelId: channel, conversationId: peer, accountId: account, messageId, ...context});
  return {message, calls, advance: ms => {time += ms;}};
}

test('adapter direct conversation, preview then confirm once, when peer has two devices', async () => {
  const {message, calls} = setup({bindings: [{...binding, device: 'other-fixture'}, binding]});
  const preview = await message('请帮我用手机打开设置', 'p1');
  assert.match(preview.text,/测试手机.*设置.*确认/);
  assert.equal(calls.length, 0);
  const results = await Promise.all([message('确认', 'c1'), message('确认', 'c1')]);
  assert.ok(results.every(v => v.handled));
  assert.equal(calls.length, 1);
  assert.equal(calls[0].who.device, binding.device);
  assert.equal(calls[0].cmd.operation, 'prepare');
  assert.match(calls[0].cmd.text,/HOME.*新画面/);
});

test('firmly bound identity for integral direct text and replies', async () => {
  for (const [e,c] of [
    [{isGroup:true},{}], [{senderId:'different'},{}], [{},{senderId:'different'}],
    [{replyToIsQuote:true},{}], [{replyToSender:'other'},{}], [{},{replyToIdFull:'x'}],
    [{threadId:'1'},{}], [{channel:'telegram'},{}], [{},{channelId:'telegram'}],
    [{},{accountId:'other'}], [{},{conversationId:'group@chatroom'}], [{},{messageId:'x'}],
  ]) {
    const {message, calls} = setup();
    assert.equal(await message('打开微信','p1',e,c),undefined);
    assert.equal(await message('确认','c1'),undefined);
    assert.deepEqual(calls,[]);
  }
  const {message} = setup({bindings: [binding,binding]});
  assert.equal(await message('打开微信','p1'),undefined);
});

test('durations, cancel, delayed and replaced plans', async () => {
  const {message,calls,advance} = setup();
  await message('打开支付宝','p1'); advance(2000);
  await message('打开微信','p2');
  assert.match((await message('确认','old',{timestamp:1_900_000_000_000})).text,/早于/);
  assert.match((await message('取消','c1')).text,/取消/);
  assert.equal(await message('确认','c2'),undefined);
  await message('打开阿柴','p3'); advance(120000);
  assert.match((await message('确认','c3')).text,/失效/);
  assert.equal(calls.length,0);
});

test('provider without stable SID deduplicates by timestamp and direct message', async () => {
  const {message,calls} = setup();
  await message('打开微信','openclaw-weixin:one');
  assert.match((await message('打开微信','openclaw-weixin:two')).text,/已处理/);
  assert.match((await message('确认','openclaw-weixin:three',{timestamp:undefined})).text,/标识/);
  await message('确认','openclaw-weixin:four');
  assert.match((await message('确认','openclaw-weixin:five')).text,/已处理/);
  assert.equal(calls.length,1);
});

test('delivery with unknown outcome never resubmits', async () => {
  const {message,calls} = setup({submit: async () => {throw Error('lost response');}});
  await message('看看我手机现在在哪个页面上','p');
  assert.match((await message('确认','c')).text,/核对原任务/);
  assert.equal(await message('确认','c2'),undefined);
  assert.equal(calls.length,1);
});

test('navigation, reading and summary keep complete anchored intent', () => {
  for (const text of ['帮我打开阿柴记账','请在手机上进入支付宝','回到桌面',
                       '帮我看一下我手机现在在哪个页面上','查看当前手机画面','汇总手机当前页面内容'])
    assert.ok(phonePlan(text),text);
  for (const text of ['我的手机','我昨天打开微信遇到了问题','打开微信并发送消息','打开支付宝并确认付款'])
    assert.equal(phonePlan(text),undefined);
});

test('confirmed or canceled provider messages remain consumed after a restart', async t => {
  const dir = mkdtempSync(join(tmpdir(),'wx-phone-'));
  t.after(() => rmSync(dir,{recursive:true,force:true}));
  const options = {journalPath:join(dir,'dedup.json')};
  const first = setup(options);
  await first.message('打开微信','p'); await first.message('确认','c');
  const fresh = setup(options);
  for (const [text,id] of [['打开微信','p'],['确认','c']])
    assert.match((await fresh.message(text,id)).text,/已处理/);
  assert.equal(fresh.calls.length,0);
  assert.ok(!readFileSync(options.journalPath,'utf8').includes(peer));
});

test('launcher labels accept Chinese and Latin names and require a fresh destination screen', () => {
  for (const name of ['计算器', '日历', 'Google Maps']) {
    const {summary, task} = phonePlan('请在手机上打开' + name);
    assert.ok(summary.includes(name));
    assert.ok(task.includes('「' + name + '」'));
    assert.match(task, /HOME.*新画面.*打开后的新画面.*首页/);
  }
  assert.equal(phonePlan('打开「日历》'), undefined);
});

test('multi-step preview repeats the request and submits the complete sequence only once', async () => {
  const {message, calls} = setup();
  const original = '先打开「再打开」，然后汇总当前页面，再回到桌面。';
  assert.ok((await message(original, 'p')).text.includes(original));
  assert.equal(calls.length, 0);
  await message('确认', 'c');
  await message('确认', 'c');
  assert.equal(calls.length, 1);
  assert.match(calls[0].cmd.text, /1）.*「再打开」.*2）读取.*3）按一次 HOME/);
});

test('a newer unsupported navigation request withdraws the preceding preview', async () => {
  const {message, calls, advance} = setup();
  await message('打开计算器', 'p1');
  advance(1000);
  assert.match((await message('打开微信并发送消息', 'p2')).text, /撤回/);
  assert.equal(await message('确认', 'c'), undefined);
  assert.equal(calls.length, 0);
});

test('out-of-order preview and ordinary chat leave the newest plan available', async () => {
  const {message, calls, advance} = setup();
  advance(1500);
  await message('打开日历', 'p1');
  assert.match((await message('打开计算器', 'p2', {timestamp:1_900_000_000_000})).text, /早于/);
  assert.equal(await message('今天怎么样', 'chat'), undefined);
  await message('确认', 'c');
  assert.match(calls[0].cmd.text, /「日历」/);
});
