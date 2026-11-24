/** @jsxImportSource react */
import { useEffect, useId, useRef, useState, type RefObject } from 'react';
import { Dialog } from 'radix-ui';
import { ArrowLeft, ArrowUpRight, X } from 'lucide-react';
import './feedback-announcement.css';
import './reference-settings.css';

const copy = {
  zh: {
    label: '使用通告', title: '欢迎反馈',
    description: '遇到问题或有建议，欢迎点击右上角「使用反馈」。',
    group: '吐槽微信群',
    continue: '下一步',
    tip: '反馈入口在这里', close: '关闭通告',
    keyTip: '密钥入口在这里',
  },
  en: {
    label: 'NOTICE',
    description: 'Use Feedback at the top right to share issues or suggestions.',
    group: 'WeChat feedback group',
    continue: 'Next',
    tip: 'Feedback is right here', close: 'Close announcement',
    keyTip: 'API key settings are here',
  },
};

type Target = { left: number; top: number; width: number; height: number };

export function FeedbackAnnouncement({ open, onAcknowledge, feedbackTarget, referenceTarget, onOpenReferenceSettings }: {
  open: boolean; onAcknowledge: () => void; feedbackTarget: RefObject<HTMLButtonElement | null>; referenceTarget?: RefObject<HTMLButtonElement | null>; onOpenReferenceSettings: () => void;
}) {
  const zh = copy.zh, en = copy.en;
  const maskId = useId().replace(/:/g, '');
  const [target, setTarget] = useState<Target | null>(null);
  const [step, setStep] = useState(1);
  const openSettingsAfterClose = useRef(false);
  const feedbackButton = useRef<HTMLButtonElement | null>(null);
  const continueButton = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (open) continueButton.current?.focus();
  }, [open, step]);

  useEffect(() => {
    if (!open) { setTarget(null); return; }
    function measure() {
      const button = step === 1 ? feedbackTarget.current : referenceTarget?.current;
      if (step === 1) feedbackButton.current = button || null;
      if (!button) { setTarget(null); return; }
      const rect = button.getBoundingClientRect();
      const next = rect.width > 0 && rect.height > 0
        ? { left: rect.left - 5, top: rect.top - 5, width: rect.width + 10, height: rect.height + 10 } : null;
      setTarget(previous => JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
    }
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(document.documentElement);
    if (feedbackTarget.current) observer.observe(feedbackTarget.current);
    if (referenceTarget?.current) observer.observe(referenceTarget.current);
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => { observer.disconnect(); window.removeEventListener('resize', measure); window.removeEventListener('scroll', measure, true); };
  }, [open, feedbackTarget, referenceTarget, step]);

  const tipRight = target ? Math.max(20, window.innerWidth - target.left - target.width) : 24;

  return <Dialog.Root open={open} onOpenChange={(next) => { if (!next) onAcknowledge(); }}>
    <Dialog.Portal>
      <Dialog.Overlay className="feedback-notice-overlay">
        <svg className="feedback-notice-shade" width="100%" height="100%" aria-hidden="true">
          <defs><mask id={maskId}><rect width="100%" height="100%" fill="white"/>{target ? <rect x={target.left} y={target.top} width={target.width} height={target.height} rx="13" fill="black"/> : null}</mask></defs>
          <rect width="100%" height="100%" fill="rgba(16, 29, 55, .47)" mask={`url(#${maskId})`}/>
        </svg>
        {target ? <>
          <div className="feedback-notice-target" style={{left:target.left,top:target.top,width:target.width,height:target.height}} aria-hidden="true"/>
          <aside className="feedback-notice-tip" style={{top:target.top + target.height + 21, right:tipRight}} aria-hidden="true">
            <span className="feedback-notice-tip-pointer"/>
            <span className="feedback-notice-tip-dot"/><div><strong lang="zh-CN">{step===1?zh.tip:zh.keyTip}</strong><span className="feedback-notice-tip-english" lang="en">{step===1?en.tip:en.keyTip}</span></div>
          </aside>
        </> : null}
      </Dialog.Overlay>
      <Dialog.Content className={`feedback-notice-card${step===2?' reference-guide-card':''}`} onPointerDownOutside={(e)=>e.preventDefault()}
        onOpenAutoFocus={(e)=>{e.preventDefault();continueButton.current?.focus();}}
        onCloseAutoFocus={(e)=>{e.preventDefault();requestAnimationFrame(()=>{
          if(openSettingsAfterClose.current){openSettingsAfterClose.current=false;onOpenReferenceSettings();}
          else if(feedbackButton.current?.isConnected)feedbackButton.current.focus();
        });}}>
        <div className="feedback-notice-intro">
          <div className="feedback-notice-eyebrow">{step===2?<button type="button" className="feedback-notice-back" aria-label="上一步 / Back" title="上一步 / Back" onClick={()=>setStep(1)}><ArrowLeft size={17} aria-hidden="true"/></button>:<span aria-hidden="true"/>}<span lang="zh-CN">{zh.label}</span><span className="feedback-notice-label-separator" aria-hidden="true">/</span><span lang="en">{en.label}</span><span className="reference-guide-progress" aria-label={`${step} / 2`}>{step} / 2</span><Dialog.Close className="feedback-notice-close" aria-label={`${zh.close} / ${en.close}`}><X size={18}/></Dialog.Close></div>
          <Dialog.Title className="feedback-notice-title">{step===1?<span lang="zh-CN">{zh.title}</span>:<><span lang="zh-CN">规则：引用文献是否不存在</span><span className="reference-guide-title-english" lang="en">Rule: Nonexistent cited references</span></>}</Dialog.Title>
          {step===1?<>
          <Dialog.Description className="feedback-notice-description"><span lang="zh-CN">{zh.description}</span><span className="feedback-notice-description-english" lang="en">{en.description}</span></Dialog.Description>
          <a className="feedback-notice-group" href="https://feedback-chat-5d9.pages.dev/" target="_blank" rel="noopener noreferrer">
            <div><strong className="feedback-notice-group-title"><span className="feedback-notice-group-primary" lang="zh-CN">{zh.group}</span><span lang="en" className="feedback-notice-group-english">{en.group}</span></strong></div><ArrowUpRight size={20} strokeWidth={1.7} aria-hidden="true"/>
          </a>
          </>:<>
            <Dialog.Description className="feedback-notice-description reference-guide-description">
              <span className="reference-guide-copy-lines" lang="zh-CN"><span>全站共享定量公共检索额度。</span><span>添加个人密钥，可使用自己的检索额度。</span></span>
              <span className="feedback-notice-description-english reference-guide-copy-lines" lang="en"><span>Public search quota is shared across the site.</span><span>Add a personal key to use your own search quota.</span></span>
            </Dialog.Description>
            <ol className="reference-guide-steps">
              <li><span className="reference-guide-step-number" aria-hidden="true">1</span><div><span lang="zh-CN">打开 API 设置，获取个人密钥</span><span lang="en">Open API settings and get a personal key</span></div></li>
              <li><span className="reference-guide-step-number" aria-hidden="true">2</span><div><span lang="zh-CN">粘贴密钥，点击「保存密钥」</span><span lang="en">Paste the key and select Save key</span></div></li>
            </ol>
          </>}
        </div>
        <footer className={`feedback-notice-footer${step===2?' reference-guide-footer':''}`}>
          {step===2?<button type="button" className="reference-guide-skip" onClick={onAcknowledge}><span lang="zh-CN">暂时跳过</span><span lang="en">Skip for now</span></button>:null}
          <button ref={continueButton} type="button" className="feedback-notice-continue" onClick={()=>{
            if(step===1)setStep(2);
            else{openSettingsAfterClose.current=true;onAcknowledge();}
          }}><span lang="zh-CN">{step===1?zh.continue:'打开 API 设置'}</span><span lang="en">{step===1?en.continue:'Open API settings'}</span></button>
        </footer>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
