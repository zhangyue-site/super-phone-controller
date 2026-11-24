import {createHash, randomUUID} from 'node:crypto';
import {mkdirSync, readFileSync, renameSync, writeFileSync, unlinkSync} from 'node:fs';
import {dirname} from 'node:path';

// OpenClaw before_dispatch handler. The Weixin adapter sets its direct peer from
// the inbound from_user_id, even in versions which don't populate SenderId.
const CHANNEL = 'openclaw-weixin';
const TTL = 120_000;
const NAVIGATION = new Map([
  ['微信', '微信'], ['支付宝', '支付宝'], ['阿柴', '阿柴记账'],
  ['阿柴记账', '阿柴记账'], ['设置', '系统设置'], ['系统设置', '系统设置'],
]);

function resolveBinding(event, ctx, bindings, targetDevice) {
  const peer = ctx.conversationId;
  if (event.channel !== CHANNEL || ctx.channelId !== CHANNEL || event.isGroup !== false ||
      !ctx.accountId || typeof peer !== 'string' || !/^[^\s@]+@im\.wechat$/.test(peer) ||
      !event.messageId || event.messageId !== ctx.messageId ||
      [event.senderId, ctx.senderId].some(value => value != null && value !== peer) ||
      [event, ctx].some(source => source.replyToIsQuote || source.replyToId || source.replyToIdFull ||
          source.replyToBody || source.replyToSender || source.parentConversationId || source.threadId)) return;
  const conversation = JSON.stringify([ctx.accountId, peer]);
  const matches = bindings.filter(b => b.channel === CHANNEL && b.sender === peer &&
    b.conversation === conversation && b.device === targetDevice);
  if (matches.length === 1) return {...matches[0], accountId: ctx.accountId, to: peer};
}

export function phonePlan(input) {
  if (typeof input !== 'string' || input.length > 500) return;
  const text = input.trim().replace(/[。！？!?]+$/, '');
  const phrase = text.replace(/^(?:麻烦|请)?(?:你)?(?:帮我)?(?:用|在)?(?:我的|我这台)?(?:手机上?)?/, '');
  const app = /^(?:打开|进入)(微信|支付宝|阿柴记账|阿柴|系统设置|设置)$/.exec(phrase);
  if (app) {
    const name = NAVIGATION.get(app[1]);
    const task = name === '系统设置'
      ? '先按 HOME 回到系统桌面，等新画面，点击唯一的设置图标；验证系统设置首页后停止。'
      : '打开' + name + '，验证应用首页后停止。';
    return {summary: '打开' + name + '，核对首页后停下。', task};
  }
  if (/^(?:返回|回到)(?:手机|系统)?桌面$/.test(phrase))
    return {summary: '返回桌面并核对新画面。', task: '按一次 HOME 返回手机桌面，用新画面核验。'};
  if (phrase === '查看当前手机画面' || /^(?:看看|看一下|查看|读一下)(?:我的|我)?手机(?:现在|当前)?(?:停)?在(?:哪个|什么)(?:页面|界面|画面)(?:上)?$/.test(phrase) ||
      /^(?:看看|查看|读取|总结|汇总)(?:一下)?(?:我的|我)?(?:手机)?(?:当前|现在)(?:的)?(?:页面|屏幕|画面)(?:内容)?$/.test(phrase) ||
      /^(?:手机|当前)?(?:屏幕|画面|界面)上有(?:什么|啥)$/.test(text))
    return {summary: '读取手机当前画面并汇总可见内容，全程只读。', task: '查看当前手机画面，汇总可见内容。只读，不点击。'};
}

function loadRecent(path) {
  if (!path) return new Map();
  try {
    const entries = JSON.parse(readFileSync(path, 'utf8'));
    if (!Array.isArray(entries) || !entries.every(entry => Array.isArray(entry) && entry.length === 2 &&
        /^[a-f0-9]{64}$/.test(entry[0]) && Number.isSafeInteger(entry[1]))) throw Error('Invalid message journal');
    return new Map(entries);
  } catch (error) {
    if (error.code === 'ENOENT') return new Map();
    throw error;
  }
}

function persistRecent(path, seen) {
  if (!path) return;
  mkdirSync(dirname(path), {recursive: true, mode: 0o700});
  const tmp = path + '.' + randomUUID();
  try {
    writeFileSync(tmp, JSON.stringify([...seen]), {mode: 0o600, flag: 'wx', flush: true});
    renameSync(tmp, path);
  } finally {
    try { unlinkSync(tmp); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}

export function createWeixinIntake({bindings, targetDevice, deviceLabel, submit, journalPath, now = Date.now, audit = () => {}}) {
  const pending = new Map();
  const seen = loadRecent(journalPath);
  return async function handle(event, ctx) {
    const binding = resolveBinding(event, ctx, bindings, targetDevice);
    if (!binding || typeof event.content !== 'string') return;
    const input = event.content.trim();
    const decision = /^(确认|取消)[。！!]?$/.exec(input)?.[1];
    const plan = phonePlan(input);
    const key = binding.conversation;
    const time = now();
    // Provider message IDs are stable across redelivery. The adapter can
    // generate a new local SID on each receipt when the provider omits one.
    const generated = String(event.messageId).startsWith('openclaw-weixin:');
    const stamp = event.timestamp;
    const id = generated ? JSON.stringify([stamp, input]) : event.messageId;
    const msgKey = createHash('sha256').update(JSON.stringify([key, id])).digest('hex');
    for (const [k, expires] of seen) if (expires <= time) seen.delete(k);
    const previous = pending.get(key);
    if (!plan && !decision) return;
    if (seen.has(msgKey)) return {handled: true, text: '这条手机指令已处理。'};
    if (!plan && !previous) return;
    if ((generated || decision) && !Number.isSafeInteger(stamp))
      return {handled: true, text: '这条微信缺少可核对的消息标识，请重新发送。'};
    if (stamp != null && (!Number.isSafeInteger(stamp) || stamp > time + 15_000 || stamp < time - TTL))
      return {handled: true, text: '这条手机指令的时间已失效，请重新发送。'};
    if (seen.size >= Math.max(bindings.length, 1) * 128)
      return {handled: true, text: '手机指令过于频繁，请稍后再试。'};
    seen.set(msgKey, time + TTL);
    try {
      persistRecent(journalPath, seen);
    } catch {
      pending.delete(key);
      return {handled: true, text: '当前无法记录消息的处理状态，手机任务未派发。'};
    }
    if (plan) {
      pending.set(key, {plan, device: binding.device, deadline: time + TTL, stamp: stamp ?? time});
      audit('phone weixin preview');
      return {handled: true, text: '我会在' + deviceLabel + '上' + plan.summary + '两分钟内回复「确认」或「取消」。'};
    }
    if (previous.deadline <= time || binding.device !== previous.device) {
      pending.delete(key);
      return {handled: true, text: '刚才的手机计划已失效，请重新说一次。'};
    }
    if (stamp != null && stamp < previous.stamp)
      return {handled: true, text: '这条回复早于当前手机计划，请核对最新计划。'};
    pending.delete(key); // Consume synchronously before the first await.
    if (decision === '取消') return {handled: true, text: '已取消这次手机任务。'};
    try {
      const result = await submit(binding, {operation: 'prepare', text: previous.plan.task});
      audit('phone weixin submitted state=' + result.state);
      return {handled: true, text: result.reply};
    } catch {
      audit('phone weixin submission unconfirmed');
      return {handled: true, text: '未取得派发回执。请先查「/phone 状态」核对原任务。'};
    }
  };
}
