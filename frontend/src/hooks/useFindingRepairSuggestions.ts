import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import type { RepairSuggestion } from '../api/repairSuggestions';
import type { PaperLintFindingItem } from '../components/paperLint/model';
type Item = PaperLintFindingItem;
type Options = { scopeKey: string | undefined; fetchSaved: (item: Item) => Promise<RepairSuggestion | null>; evaluate?: (item: Item, force: boolean) => Promise<{response: RepairSuggestion}>; supportedRuleIds?: Set<string> };
function createQueue(limit: number) {
  let active = 0;
  const pending: (() => void)[] = [];
  function advance() { while (active < limit && pending.length) pending.shift()!(); }
  return (work: () => Promise<void>) => new Promise<void>((resolve, reject) => {
    pending.push(() => { active++; void Promise.resolve().then(work).then(resolve, reject).finally(() => {active--; advance();}); });
    advance();
  });
}
export function useFindingRepairSuggestions({scopeKey, fetchSaved, evaluate, supportedRuleIds}: Options) {
  const [repairSuggestionByFindingKey, setSuggestions] = useState<Record<string, RepairSuggestion | undefined>>({});
  const [repairSuggestionErrorByFindingKey, setErrors] = useState<Record<string, string | undefined>>({});
  const [repairSuggestionLoadingByFindingKey, setLoading] = useState<Record<string, boolean>>({});
  const loaded = useRef(new Set<string>());
  const inFlight = useRef(new Set<string>());
  const epoch = useRef(0);
  const [enqueueRead] = useState(() => createQueue(3));
  const [enqueueGeneration] = useState(() => createQueue(2));
  useLayoutEffect(() => {
    epoch.current++; loaded.current = new Set(); inFlight.current = new Set();
    setSuggestions({}); setErrors({}); setLoading({});
    return () => {epoch.current++;};
  }, [scopeKey]);
  const supportsRepairSuggestion = useCallback((item: Item) => !item.finding.prompt_only && (!supportedRuleIds || supportedRuleIds.has(item.ruleRun.rule_id)), [supportedRuleIds]);
  const run = useCallback(async (item: Item, force: boolean) => {
    if (!scopeKey || !supportsRepairSuggestion(item) || inFlight.current.has(item.key) || (!force && loaded.current.has(item.key))) return;
    const generation = epoch.current;
    loaded.current.add(item.key); inFlight.current.add(item.key);
    setLoading(current => ({...current, [item.key]: true}));
    setErrors(current => ({...current, [item.key]: undefined}));
    try {
      let response: RepairSuggestion | null = null;
      if (!force) await enqueueRead(async () => {
        if (generation === epoch.current) response = await fetchSaved(item);
      });
      if (generation !== epoch.current) return;
      if (!response && evaluate) await enqueueGeneration(async () => {
        if (generation === epoch.current) response = (await evaluate(item, force)).response;
      });
      if (generation === epoch.current && response) setSuggestions(current => ({...current, [item.key]: response!}));
    } catch (cause) {
      const response = (cause as { response?: { status?: unknown; data?: { message?: unknown } } })?.response;
      const responseMessage = response?.data?.message;
      const message = response?.status === 429
        ? '当前 AI 服务请求较多，请稍后重试'
        : typeof responseMessage === 'string' && responseMessage.trim()
          ? responseMessage
          : cause instanceof Error ? cause.message : '修复建议暂不可用';
      if (generation === epoch.current) setErrors(current => ({...current, [item.key]: message}));
    } finally {
      if (generation === epoch.current) {
        inFlight.current.delete(item.key);
        setLoading(current => ({...current, [item.key]: false}));
      }
    }
  }, [scopeKey, supportsRepairSuggestion, enqueueRead, enqueueGeneration, fetchSaved, evaluate]);
  const loadRepairSuggestion = useCallback((item: Item) => run(item, false), [run]);
  const generateRepairSuggestion = useCallback((item: Item) => run(item, true), [run]);
  return {repairSuggestionByFindingKey, repairSuggestionErrorByFindingKey, repairSuggestionLoadingByFindingKey,
    repairSuggestionLoadingKey: Object.keys(repairSuggestionLoadingByFindingKey).find(key => repairSuggestionLoadingByFindingKey[key]) || null,
    supportsRepairSuggestion, loadRepairSuggestion, generateRepairSuggestion};
}
