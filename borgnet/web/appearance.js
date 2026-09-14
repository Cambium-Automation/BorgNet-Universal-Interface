'use strict';
(() => {
  const sections = {
    all: ['Entire interface', 'body'],
    sidebar: ['Connections panel', '.sidebar'],
    workspace: ['Workspace', '.workspace'],
    models: ['Model cards', '.connection'],
    composer: ['Message box', '.composer'],
    navigation: ['Navigation', '.workspace-nav'],
    answers: ['Answer cards', '.result'],
    context: ['Context cards', '.context-card, .mcp-card']
  };
  const key = 'borgnet-appearance-v1';
  let preferences = {};
  try { preferences = JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch {}
  const $ = id => document.getElementById(id);
  const style = document.getElementById('appearanceOverrides');
  const fields = {background:'appearanceBackground',text:'appearanceText',muted:'appearanceMuted',toggle:'appearanceToggle',highlight:'appearanceHighlight'};
  const valid = value => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value);
  function clean(value) {
    if (!value || !Object.keys(fields).every(name => valid(value[name]))) return null;
    if (!Number.isFinite(value.opacity) || value.opacity < 0 || value.opacity > 98) return null;
    return value;
  }
  function rgba(hex, opacity) {return `rgba(${[1,3,5].map(i => parseInt(hex.slice(i,i+2),16)).join(',')},${opacity/100})`;}
  function rules(selector, p) {
    return `${selector}{background-color:${rgba(p.background,p.opacity)}!important;--text:${p.text}!important;--muted:${p.muted}!important;--accent:${p.toggle}!important;--custom-highlight:${p.highlight};color:${p.text}}
      ${selector.split(',').map(s=>`${s.trim()} .connection-toggle[aria-checked=true] .toggle-track`).join(',')}{background:${p.toggle};border-color:${p.toggle}}
      ${selector.split(',').map(s=>`${s.trim()} .tabs button.active`).join(',')}{background:${rgba(p.highlight,Math.max(22,p.opacity))}!important}
      ${selector.split(',').map(s=>`${s.trim()} .tabs button:hover:not(:disabled)`).join(',')}{background:${rgba(p.highlight,70)}!important}`;
  }
  function apply() {
    const blocks=[];
    const blur=Number.isFinite(preferences.backgroundBlurRadius)?Math.max(0,Math.min(100,preferences.backgroundBlurRadius)):null;
    const bridge=window.webkit?.messageHandlers?.borgnetBlur;
    if(bridge)bridge.postMessage(blur===null?{reset:true}:{radius:blur});
    else if(blur!==null)blocks.push(`.shell{-webkit-backdrop-filter:blur(${blur}px);backdrop-filter:blur(${blur}px)}`);
    const all=clean(preferences.all);
    if(all) {
      // Paint each major surface so the opacity control also works over native glass.
      blocks.push(rules('body',all));
      for(const [id,[,selector]] of Object.entries(sections))if(id!=='all')blocks.push(rules(selector,all));
    }
    for(const [id,[,selector]] of Object.entries(sections))if(id!=='all') {const p=clean(preferences[id]);if(p)blocks.push(rules(selector,p));}
    blocks.push('.connection-toggle[aria-checked=true] .toggle-track::after{background:var(--accent-text)}');
    // Modify the same-origin stylesheet through CSSOM. Inline style text is
    // deliberately blocked by the application's content security policy.
    const sheet=style.sheet;
    if(!sheet)throw new Error('Appearance stylesheet is unavailable. Reload the workspace.');
    while(sheet.cssRules.length)sheet.deleteRule(0);
    for(const rule of blocks.join('\n').split('}').map(part=>part.trim()).filter(Boolean))sheet.insertRule(rule+'}',sheet.cssRules.length);
  }
  function toHex(value, fallback) {
    if(valid(value))return value;
    const match=value.match(/^rgba?\(\s*(\d+)[, ]+\s*(\d+)[, ]+\s*(\d+)/);
    return match?'#'+match.slice(1,4).map(v=>Number(v).toString(16).padStart(2,'0')).join(''):fallback;
  }
  function populate() {
    $('appearanceBlur').value=preferences.backgroundBlurRadius??0;
    $('appearanceBlurValue').textContent=(preferences.backgroundBlurRadius??0)+' px';
    const id=$('appearanceSection').value;
    const node=document.querySelector(sections[id][1])||document.body;
    const css=getComputedStyle(node);
    const p=clean(preferences[id])||clean(preferences.all)||{
      background:toHex(css.backgroundColor,toHex(css.getPropertyValue('--bar').trim(),'#233234')),
      text:toHex(css.getPropertyValue('--text').trim(),'#e7eeec'),
      muted:toHex(css.getPropertyValue('--muted').trim(),'#bdc7c9'),
      toggle:toHex(css.getPropertyValue('--accent').trim(),'#b9ded0'),
      highlight:toHex(css.getPropertyValue('--accent').trim(),'#b9ded0'),opacity:8
    };
    for(const [name,input] of Object.entries(fields))$(input).value=p[name];
    $('appearanceOpacity').value=p.opacity;$('appearanceOpacityValue').textContent=p.opacity+'%';
    $('appearanceSaveState').textContent=clean(preferences[id])?'Custom appearance saved.':'Using inherited or theme appearance.';
  }
  function update() {
    const p={opacity:Number($('appearanceOpacity').value)};
    for(const [name,input] of Object.entries(fields))p[name]=$(input).value;
    preferences[$('appearanceSection').value]=p;apply();
    $('appearanceOpacityValue').textContent=p.opacity+'%';
    try{localStorage.setItem(key,JSON.stringify(preferences));$('appearanceSaveState').textContent='Saved on this device.';}catch{$('appearanceSaveState').textContent='Preview applied; device storage is unavailable.';}
  }
  for(const [id,[label]] of Object.entries(sections))$('appearanceSection').add(new Option(label,id));
  $('appearanceSettings').addEventListener('click',()=>{populate();window.borgnetTransitions.openDialog($('appearanceDialog'));});
  $('appearanceSection').addEventListener('change',populate);
  $('appearanceBlur').addEventListener('input',()=>{
    preferences.backgroundBlurRadius=Number($('appearanceBlur').value);apply();
    $('appearanceBlurValue').textContent=preferences.backgroundBlurRadius+' px';
    try{localStorage.setItem(key,JSON.stringify(preferences));$('appearanceSaveState').textContent='Saved on this device.';}catch{$('appearanceSaveState').textContent='Preview applied; device storage is unavailable.';}
  });
  window.addEventListener('borgnet-native-appearance',apply);
  window.addEventListener('borgnet-blur-status',event=>{
    $('appearanceBlur').disabled=!event.detail.available;
    $('appearanceBlurStatus').textContent=event.detail.available?'Softens background detail without changing tint or opacity. Text stays sharp.':'Adjustable desktop blur is unavailable on this macOS version.';
  });
  for(const input of [...Object.values(fields),'appearanceOpacity'])$(input).addEventListener('input',update);
  for(const id of ['closeAppearance','doneAppearance'])$(id).addEventListener('click',()=>window.borgnetTransitions.closeDialog($('appearanceDialog')));
  function reset(all) {if(all)preferences={};else delete preferences[$('appearanceSection').value];try{localStorage.setItem(key,JSON.stringify(preferences));}catch{}apply();populate();}
  $('resetAppearanceSection').addEventListener('click',()=>reset(false));
  $('resetAppearanceAll').addEventListener('click',()=>reset(true));
  apply();
})();
