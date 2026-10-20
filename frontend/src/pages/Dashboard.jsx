import React, { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float, MeshDistortMaterial, Sparkles } from "@react-three/drei";
import { getNotesList, getQuizAttempts, getPlanner, getActiveStudySession, startStudySession, pauseStudySession, resumeStudySession, heartbeatStudySession, completeStudySession, startRecommendation, completeRecommendation, dismissRecommendation } from "../services/api";
import "../styles/dashboard-reference.css";

const paths = {
  home: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/></>,
  upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/></>,
  notes: <><path d="M6 3h9l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM14 3v5h5M8 12h8M8 16h6"/></>,
  quiz: <><rect x="3" y="4" width="18" height="16" rx="3"/><path d="M8 9h.01M12 9h.01M16 9h.01M8 14l2 2 5-5"/></>,
  calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18M8 14h3M8 17h6"/></>,
  chart: <path d="M4 20V12h4v8M10 20V5h4v15M16 20V9h4v11"/>,
  target: <><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><path d="M12 12 21 3M16 3h5v5"/></>,
  clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/></>,
  bulb: <path d="M9 18h6M10 22h4M8 14a7 7 0 1 1 8 0c-1 .7-1 2-1 2H9s0-1.3-1-2z"/>,
  pie: <path d="M12 3v9h9A9 9 0 1 1 12 3z"/>,
  arrow: <path d="M5 12h14M13 6l6 6-6 6"/>,
  spark: <path d="m12 3 2.3 5.2L20 10l-5.7 1.8L12 17l-2.3-5.2L4 10l5.7-1.8z"/>
};
function Icon({ name = "spark", size = 18 }) { return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.spark}</svg>; }

function Core() {
  const orb = useRef(null), ring = useRef(null);
  useFrame(({ pointer, clock }) => {
    if (!orb.current || !ring.current) return;
    orb.current.rotation.x += (pointer.y * .2 - orb.current.rotation.x) * .04;
    orb.current.rotation.y += (pointer.x * .3 + clock.elapsedTime * .07 - orb.current.rotation.y) * .04;
    ring.current.rotation.y += .003;
    ring.current.rotation.x = .9 + pointer.y * .15;
  });
  return <group><Float speed={1.2} rotationIntensity={.25} floatIntensity={.45}><mesh ref={orb}><icosahedronGeometry args={[.9, 5]}/><MeshDistortMaterial color="#64b6ac" roughness={.2} metalness={.35} distort={.22} speed={1.5}/></mesh></Float><mesh ref={ring} rotation={[.9,.3,-.45]}><torusGeometry args={[1.22,.025,12,100]}/><meshStandardMaterial color="#c0fdfb" metalness={.75} emissive="#119da4" emissiveIntensity={.65}/></mesh><mesh rotation={[1.5,.2,.4]}><torusGeometry args={[1.42,.012,8,100]}/><meshStandardMaterial color="#e29578" metalness={.6} emissive="#e29578" emissiveIntensity={.35}/></mesh><Sparkles count={38} scale={3.8} size={2} speed={.28} color="#c0fdfb"/></group>;
}
function Hero() { return <div className="rf-hero-3d"><Canvas camera={{position:[0,0,4.1],fov:42}} dpr={[1,1.5]} gl={{alpha:true,antialias:true}}><ambientLight intensity={1.3}/><directionalLight position={[3,4,4]} intensity={2} color="#c0fdfb"/><pointLight position={[-3,-1,2]} intensity={18} color="#119da4"/><pointLight position={[2,-2,-2]} intensity={10} color="#e29578"/><Suspense fallback={null}><Core/></Suspense></Canvas><div className="rf-orb-caption"><i/> YOUR LEARNING CORE</div></div>; }
function ThreeIcon({kind="spark",size=32}) {
  let mesh;
  if(kind==="target") mesh=<><mesh><torusGeometry args={[.23,.018,8,32]}/><meshStandardMaterial color="#e29578"/></mesh><mesh><torusGeometry args={[.14,.014,8,32]}/><meshStandardMaterial color="#c0fdfb"/></mesh><mesh><sphereGeometry args={[.05,16,16]}/><meshPhysicalMaterial color="#fad4c0" metalness={.2} transmission={.2}/></mesh></>;
  else if(kind==="clock") mesh=<><mesh><cylinderGeometry args={[.25,.25,.07,32]}/><meshPhysicalMaterial color="#64b6ac" metalness={.25} transmission={.2}/></mesh><mesh position={[0,0,.05]}><boxGeometry args={[.025,.14,.025]}/><meshStandardMaterial color="#fee9e1"/></mesh><mesh position={[.06,-.04,.06]} rotation={[0,0,.8]}><boxGeometry args={[.025,.11,.02]}/><meshStandardMaterial color="#e29578"/></mesh></>;
  else if(kind==="notes"||kind==="calendar") mesh=<><mesh><boxGeometry args={kind==="calendar"?[.36,.32,.06]:[.32,.4,.07]}/><meshPhysicalMaterial color="#c0fdfb" roughness={.16} metalness={.18} transmission={.2}/></mesh><mesh position={[0,.1,.05]}><boxGeometry args={[.34,.05,.02]}/><meshStandardMaterial color="#e29578"/></mesh>{[-.04,-.12].map(y=><mesh key={y} position={[0,y,.05]}><boxGeometry args={[.21,.014,.01]}/><meshStandardMaterial color="#119da4"/></mesh>)}</>;
  else if(kind==="chart"||kind==="pie") mesh=<>{[.15,.23,.32].map((h,i)=><mesh key={i} position={[-.18+i*.17,-.09+h/2,0]}><boxGeometry args={[.09,h,.09]}/><meshPhysicalMaterial color={i===1?"#fad4c0":"#119da4"} metalness={.2} transmission={.2}/></mesh>)}</>;
  else mesh=<><mesh><icosahedronGeometry args={[.22,1]}/><meshPhysicalMaterial color="#64b6ac" roughness={.16} metalness={.18} transmission={.2}/></mesh><mesh rotation={[.7,.3,.4]}><torusGeometry args={[.31,.012,8,48]}/><meshStandardMaterial color="#e29578" metalness={.5}/></mesh></>;
  return <span className="rf-glass-icon" style={{width:size,height:size}} aria-hidden="true"><Canvas camera={{position:[0,0,1.65],fov:48}} dpr={[1,1.5]} gl={{alpha:true,antialias:true}}><ambientLight intensity={1.5}/><directionalLight position={[2,3,4]} intensity={2} color="#fee9e1"/><pointLight position={[-2,-1,2]} intensity={5} color="#119da4"/><group>{mesh}</group></Canvas></span>;
}
function Panel({icon,title,subtitle,action,onAction,children,cls=""}) { return <section className={"rf-panel "+cls}><header className="rf-panel-title"><div className="rf-title-left"><span className="rf-small-icon"><Icon name={icon}/></span><span><b>{title}</b><small>{subtitle}</small></span></div>{action&&<button className="rf-link-button" onClick={onAction}>{action} <Icon name="arrow" size={13}/></button>}</header>{children}</section>; }
const noteTitle=(n)=>n.title||n.filename||n.original_filename||n.name||"Untitled study note";
const noteId=(n)=>n.id??n.note_id??n.document_id;
const recent=(v)=>{if(!v)return "Recently";const d=new Date(v);if(Number.isNaN(d.getTime()))return String(v);const days=Math.max(0,Math.floor((Date.now()-d.getTime())/86400000));return days===0?"Today":days===1?"Yesterday":days<7?days+" days ago":d.toLocaleDateString(undefined,{day:"numeric",month:"short"});};
const prettyMinutes=(n)=>{n=Math.max(0,Number(n)||0);return n>=60?(Math.floor(n/60)+"h"+(n%60?" "+(n%60)+"m":"")):n+"m";};
const estimateTaskMinutes=(task)=>{const direct=Number(task?.duration_minutes);if(Number.isFinite(direct)&&direct>0)return direct;const estimate=String(task?.est||"");const hours=estimate.match(/(\d+)\s*h/i);if(hours)return Number(hours[1])*60;const minutes=estimate.match(/(\d+)\s*min/i);return minutes?Number(minutes[1]):20;};
const plannerTaskOverdue=(task,now=new Date())=>{
  const scheduled=task?.scheduled_at?new Date(task.scheduled_at):null;
  const raw=task?.original_due_date||task?.due_date;
  const deadline=raw?new Date(raw):null;
  const validScheduled=scheduled&&!Number.isNaN(scheduled.getTime());
  const validDeadline=deadline&&!Number.isNaN(deadline.getTime());
  let deadlinePassed=false;
  if(validDeadline){
    if(typeof raw==="string"&&/^\d{4}-\d{2}-\d{2}$/.test(raw)){
      const key=(value)=>value.getFullYear()+"-"+String(value.getMonth()+1).padStart(2,"0")+"-"+String(value.getDate()).padStart(2,"0");
      deadlinePassed=key(deadline)<key(now);
    } else deadlinePassed=deadline.getTime()<now.getTime();
  }
  return Boolean((validScheduled&&scheduled.getTime()<now.getTime())||deadlinePassed);
};

export default function Dashboard({data,loading,onNavigate,onRefresh,toast,onToggleSidebar}) {
  const [query,setQuery]=useState(""),[notes,setNotes]=useState([]),[attempts,setAttempts]=useState([]),[tasks,setTasks]=useState([]),[loadingExtras,setLoadingExtras]=useState(false),[activeStudySession,setActiveStudySession]=useState(null),[studyBusy,setStudyBusy]=useState(false);const [clockNow,setClockNow]=useState(Date.now());
  useEffect(()=>{let live=true;setLoadingExtras(true);Promise.allSettled([getNotesList(),getQuizAttempts(null,100),getPlanner(),getActiveStudySession()]).then(([n,q,p,active])=>{if(!live)return;if(n.status==="fulfilled"){const v=n.value;setNotes((Array.isArray(v)?v:v?.notes||v?.items||v?.documents||[]).map(x=>({...x,_title:noteTitle(x),_id:noteId(x)})));}if(q.status==="fulfilled"){const v=q.value;setAttempts(Array.isArray(v)?v:v?.attempts||v?.items||[]);}if(p.status==="fulfilled"){const v=p.value;setTasks(Array.isArray(v)?v:v?.tasks||[]);}if(active.status==="fulfilled")setActiveStudySession(active.value?.active||null);setLoadingExtras(false);});return()=>{live=false;};},[data?.analytics?.quizzes_attempted,data?.analytics?.uploaded_files_count,data?.analytics?.notes_count,data?.analytics?.study_minutes,data?.analytics?.completed_activities,data?.recent_activity?.length]);
  useEffect(()=>{
    if(!activeStudySession?.session_id) return;
    let live=true;
    const clock=setInterval(()=>{if(live)setClockNow(Date.now());},1000);
    const heartbeat=setInterval(async()=>{
      if(!live || activeStudySession.status!=="active") return;
      try {
        const result=await heartbeatStudySession(activeStudySession.session_id);
        if(live && result?.session) setActiveStudySession(result.session);
      } catch {
        // The backend safely pauses stale sessions after the heartbeat timeout.
      }
    },30000);
    return()=>{live=false;clearInterval(clock);clearInterval(heartbeat);};
  },[activeStudySession?.session_id,activeStudySession?.status]);
  const sessionElapsedSeconds=(session)=>{
    if(!session) return 0;
    const closed=(session.intervals||[]).reduce((sum,interval)=>sum+Math.max(0,Number(interval.duration_seconds)||0),0);
    if(session.status!=="active" || !session.active_interval_started_at) return Number(session.duration_seconds)||closed;
    const started=Date.parse(session.active_interval_started_at);
    return closed+(Number.isFinite(started)?Math.max(0,Math.floor((clockNow-started)/1000)):0);
  };
  const liveStudySeconds=sessionElapsedSeconds(activeStudySession);
  const liveStudyLabel=liveStudySeconds>=3600
    ? Math.floor(liveStudySeconds/3600)+"h "+Math.floor((liveStudySeconds%3600)/60)+"m"
    : Math.floor(liveStudySeconds/60)+"m";
  const a=data?.analytics||{},topics=data?.topics||[],kpi=(id)=>(data?.kpis||[]).find(x=>x.id===id);
  const shownNotes=useMemo(()=>notes.filter(n=>!query||n._title.toLowerCase().includes(query.trim().toLowerCase())).slice(0,3),[notes,query]);
  const scores=useMemo(()=>{const rows=attempts.length?attempts.slice(0,8).reverse():(a.emoji_performance_history||[]).slice(0,8).reverse();return rows.map((q,i)=>({x:rows.length===1?330:i/(rows.length-1)*660,y:8+(100-Math.max(0,Math.min(100,Number(q.score??q.percentage??0))))*1.4,score:Number(q.score??q.percentage??0),title:q.topic_label||q.note_title||q.topic||q.feedback||"Quiz "+(i+1)}));},[attempts,a.emoji_performance_history]);
  const line=scores.map((p,i)=>(i?"L":"M")+p.x+" "+p.y).join(" "),area=scores.length?line+" L "+scores[scores.length-1].x+" 148 L "+scores[0].x+" 148 Z":"";
  const activity=(data?.activity_heatmap||[]).slice(-12).flatMap(c=>c).map(c=>({level:({"":0,l1:1,l2:2,l3:3,l4:4})[c.lvl]??0,label:(c.date||"")+" · "+(c.tip||"No activity")}));
  const studyMins=Number(a.study_minutes)||0,mastered=Number(a.topics_mastered)||0,topicCount=Math.max(topics.length,mastered);
  const recommendations=(data?.recommendations||[]).slice(0,3);
  useEffect(()=>{const refreshVisible=()=>{if(document.visibilityState==="visible")onRefresh?.();};const timer=window.setInterval(refreshVisible,30000);window.addEventListener("focus",refreshVisible);document.addEventListener("visibilitychange",refreshVisible);return()=>{window.clearInterval(timer);window.removeEventListener("focus",refreshVisible);document.removeEventListener("visibilitychange",refreshVisible);};},[onRefresh]);
  async function startRecommendedAction(recommendation) {
    try {
      await startRecommendation(recommendation.id);
    } catch (error) {
      toast?.(error?.message || "Could not update recommendation status.", "coral");
      return;
    }
    const action = recommendation.action_payload || {};
    const topic = action.concept || recommendation.concept || action.topic || recommendation.topic || "";
    const noteId = action.note_id || null;
    if (action.type === "open_planner_task") {
      onNavigate("planner");
      return;
    }
    if ((action.type === "deep_study" || action.type === "revise_topic") && noteId) {
      onNavigate("notes", { noteId });
      return;
    }
    onNavigate("quiz", { quizNoteId: noteId, quizTopic: topic, recommendationId: recommendation.id });
  }
  async function practiceRecommendation(recommendation) {
    try {
      await startRecommendation(recommendation.id);
    } catch (error) {
      toast?.(error?.message || "Could not start this recommendation.", "coral");
      return;
    }
    const action = recommendation.action_payload || {};
    onNavigate("quiz", {
      quizNoteId: action.note_id || null,
      quizTopic: action.concept || recommendation.concept || action.topic || recommendation.topic || "",
      recommendationId: recommendation.id,
    });
  }
  async function markRecommendationComplete(recommendation) {
    try {
      await completeRecommendation(recommendation.id);
      toast?.("Recommendation marked complete.", "teal");
      await onRefresh?.();
    } catch (error) {
      toast?.(error?.message || "Could not complete recommendation.", "coral");
    }
  }
  async function dismissRecommendationCard(recommendation) {
    try {
      await dismissRecommendation(recommendation.id);
      toast?.("Recommendation dismissed.", "teal");
      await onRefresh?.();
    } catch (error) {
      toast?.(error?.message || "Could not dismiss recommendation.", "coral");
    }
  }
  const activityBreakdown=a.activity_breakdown||{};
  const focusCounts=[Number(activityBreakdown.quiz_practice)||0,Number(activityBreakdown.notes_uploads)||0,Number(activityBreakdown.other)||0];
  const focusTotal=focusCounts.reduce((sum,value)=>sum+value,0);
  const donut=focusTotal?(()=>{const p=focusCounts[0]/focusTotal*100,q=(focusCounts[0]+focusCounts[1])/focusTotal*100;return "conic-gradient(var(--rf-teal) 0 "+p+"%,var(--rf-mint) "+p+"% "+q+"%,var(--rf-coral) "+q+"% 100%)";})():"var(--rf-panel)";
  if(loading)return <div className="rf-dashboard-loading">Loading your learning dashboard…</div>;
  if(!data)return <div className="rf-dashboard-loading">Dashboard data unavailable. <button onClick={onRefresh}>Try again</button></div>;
  const noteCount=Number(a.notes_count??notes.filter(note=>note.source==="generated").length)||0;
  const completedActivities=Number(a.completed_activities)||0;
  const pendingRevisionTasks=tasks.filter(t=>!t.done&&!["completed","cancelled","skipped"].includes(t.status));
  const overdueRevisionTasks=pendingRevisionTasks.filter(t=>plannerTaskOverdue(t));
  const plannedRevisionMinutes=pendingRevisionTasks.reduce((sum,t)=>sum+estimateTaskMinutes(t),0);
  const stats=[
    {title:"Notes created",value:String(noteCount),pct:Math.min(100,noteCount*10),note:noteCount?"Saved generated notes":"Upload or create a note to begin",icon:"notes",tone:"peach",view:"notes"},
    {title:"Study time",value:activeStudySession?prettyMinutes(Math.floor(liveStudySeconds/60)):"0m",pct:activeStudySession?Math.min(100,liveStudySeconds/720):0,note:activeStudySession?(activeStudySession.status==="paused"?"Timer paused · active intervals preserved":"Live timer · updates every second"):"Start a timer to record study time",icon:"clock",tone:"mint"},
    {title:"Quizzes completed",value:String(a.quizzes_attempted??kpi("quizzes")?.value??0),pct:Math.min(100,Number(a.quizzes_attempted||0)*5),note:a.average_score!==undefined&&a.quizzes_attempted?a.average_score+"% average score":"Saved attempts appear here",icon:"notes",tone:"ice",view:"quiz"},
    {title:"Learning progress",value:mastered+" / "+topicCount,pct:topicCount?mastered/topicCount*100:0,note:completedActivities+" completed activities · "+topics.length+" tracked topics",icon:"chart",tone:"coral",view:"notes"}
  ];
  return <div className="rf-dashboard"><main className="rf-main"><header className="rf-topbar"><button className="rf-menu-button" aria-label="Toggle navigation" onClick={onToggleSidebar}>☰</button><label className="rf-search"><span>⌕</span><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search your notes and topics…"/><kbd>Ctrl K</kbd></label><span className="rf-top-spacer"/><span className="rf-streak-pill">✦ {data.user?.streak??0} day streak</span><button className="rf-notification" aria-label="Notifications" onClick={()=>toast((data.recent_activity||[]).length+" recent learning activities.","teal")}>♧<i/></button><span className="rf-profile-dot">{data.user?.initials||"SA"}</span><span className="rf-profile-name">Welcome back,<b>{data.user?.name||"LEARNER"}</b></span></header>
      <section className="rf-welcome"><div><div className="rf-overline">YOUR PERSONAL LEARNING SPACE</div><h1>Your learning, <em>in motion.</em></h1><p>Small steps today. Stronger understanding tomorrow.</p><span className="rf-welcome-chip"><i/>Consistency is your superpower</span></div><Hero/></section>
      <div className="rf-metric-grid">{stats.map(s=><article key={s.title} className={"rf-metric-card tone-"+s.tone+(s.title==="Study time"?" rf-study-time-card":"")} style={s.title==="Study time"?{minHeight:174,height:"auto",overflow:"visible",zIndex:2}:undefined} role={s.view?"button":undefined} tabIndex={s.view?0:undefined} onClick={()=>s.view&&onNavigate(s.view)}><div className="rf-metric-card-top"><ThreeIcon kind={s.icon} size={36}/><span>↗</span></div><label>{s.title}</label><strong>{s.value}</strong><div className="rf-mini-track"><span style={{width:Math.max(0,Math.min(100,s.pct))+"%"}}/></div><small><Icon name="arrow" size={12}/>{s.note}</small>{s.title==="Study time"&&<div className="rf-study-timer-controls" aria-label="Study timer controls" style={{display:"flex",gap:6,flexWrap:"wrap",marginTop:10}}>{!activeStudySession?<button type="button" disabled={studyBusy} onClick={async(e)=>{e.stopPropagation();setStudyBusy(true);try{const result=await startStudySession("Dashboard study");setActiveStudySession(result?.session||null);setClockNow(Date.now());toast?.("Study timer started.","teal");}catch(error){toast?.(error?.message||"Could not start study timer.","coral");}finally{setStudyBusy(false);}}} style={{fontSize:11,padding:"5px 9px",borderRadius:8,border:"1px solid var(--rf-teal)",background:"transparent",color:"var(--rf-mint)",cursor:"pointer"}}>▶ Start</button>:<><button type="button" disabled={studyBusy} onClick={async(e)=>{e.stopPropagation();setStudyBusy(true);try{const result=activeStudySession.status==="paused"?await resumeStudySession(activeStudySession.session_id):await pauseStudySession(activeStudySession.session_id);setActiveStudySession(result?.session||activeStudySession);setClockNow(Date.now());toast?.(activeStudySession.status==="paused"?"Study timer resumed.":"Study timer paused.","teal");}catch(error){toast?.(error?.message||"Could not update study timer.","coral");}finally{setStudyBusy(false);}}} style={{fontSize:11,padding:"5px 9px",borderRadius:8,border:"1px solid var(--rf-teal)",background:"transparent",color:"var(--rf-mint)",cursor:"pointer"}}>{activeStudySession.status==="paused"?"▶ Resume":"Ⅱ Pause"}</button><button type="button" disabled={studyBusy} onClick={async(e)=>{e.stopPropagation();setStudyBusy(true);try{const result=await completeStudySession(activeStudySession.session_id);const mins=Math.floor((Number(result?.session?.duration_seconds)||0)/60);setActiveStudySession(null);setClockNow(Date.now());toast?.("Study time saved: "+prettyMinutes(mins),"teal");await onRefresh?.();}catch(error){toast?.(error?.message||"Could not finish study timer.","coral");}finally{setStudyBusy(false);}}} style={{fontSize:11,padding:"5px 9px",borderRadius:8,border:"1px solid var(--rf-coral)",background:"transparent",color:"var(--rf-coral)",cursor:"pointer"}}>■ Finish</button><button type="button" disabled={studyBusy} onClick={async(e)=>{e.stopPropagation();setStudyBusy(true);try{await completeStudySession(activeStudySession.session_id);const result=await startStudySession("Dashboard study");setActiveStudySession(result?.session||null);setClockNow(Date.now());toast?.("Study timer restarted from 0m.","teal");await onRefresh?.();}catch(error){toast?.(error?.message||"Could not restart study timer.","coral");}finally{setStudyBusy(false);}}} style={{fontSize:11,padding:"5px 9px",borderRadius:8,border:"1px solid var(--rf-teal)",background:"transparent",color:"var(--rf-mint)",cursor:"pointer"}}>↻ Restart</button></>}</div>}</article>)}</div>
      <div className="rf-main-grid"><Panel cls="rf-journey-panel" icon="spark" title="Your learning journey" subtitle="One clear next step at a time." action="Full journey" onAction={()=>onNavigate("journey")}><div className="rf-journey-steps">{[["01","Review notes","Reconnect with recent study material.",notes.length?"Ready":"Start here","notes"],["02","Practice quiz","Check what really stuck.",a.quizzes_attempted?"In progress":"Up next","quiz"],["03","Revise weak topics","Turn gaps into strengths.",(a.weak_topics||[]).length?"Recommended":"Up next","quiz"],["04","Next session","Keep your momentum moving.",pendingRevisionTasks.length?"Queued":"Plan session","planner"]].map(([num,title,desc,status,view])=><div key={num} className={"rf-journey-step rf-step-"+num}><span className="rf-step-node">{num==="01"&&notes.length?"✓":num}</span><b>{title}</b><p>{desc}</p><button className="rf-step-status" onClick={()=>onNavigate(view)}>{status}</button></div>)}</div><footer className="rf-journey-bottom"><span/>YOUR PATH IS TAKING SHAPE<span/></footer></Panel>
        <Panel cls="rf-revision-panel" icon="calendar" title="Revision plan" subtitle="Your next focused sessions." action="View plan" onAction={()=>onNavigate("planner")}><div className="rf-plan-summary"><div><small>Pending sessions</small><b>{pendingRevisionTasks.length}</b></div><div className={overdueRevisionTasks.length?"warning":""}><small>Overdue</small><b>{overdueRevisionTasks.length}</b></div><div><small>Planned time</small><b>{prettyMinutes(plannedRevisionMinutes)}</b></div></div><div className="rf-revision-list">{pendingRevisionTasks.slice(0,4).map((t,i)=><button className="rf-revision-item" key={t.id??t.title} onClick={()=>onNavigate("planner")}><span className="rf-revision-node">{String(i+1).padStart(2,"0")}</span><span className="rf-revision-copy"><small>{t.date||(t.day==="today"?"Today":"Upcoming")}</small><b>{t.title}</b></span><span className="rf-upcoming">Planned</span></button>)}{!pendingRevisionTasks.length&&<p className="rf-empty">{loadingExtras?"Loading your plan…":"No pending sessions. Open the planner to plan your next session."}</p>}</div></Panel></div>
      <div className="rf-secondary-grid"><Panel cls="rf-notes-panel" icon="notes" title="Recent notes" subtitle="Pick up where you left off." action="All notes" onAction={()=>onNavigate("notes")}><div className="rf-recent-notes">{shownNotes.map((n,i)=><button key={n._id??n._title} className="rf-recent-note" onClick={()=>n._id?onNavigate("notes",{noteId:n._id}):onNavigate("notes")}><ThreeIcon kind={i===0?"notes":i===1?"chart":"calendar"} size={32}/><span><b>{n._title}</b><small>{n.page_count?n.page_count+" pages · ":""}{recent(n.updated_at||n.created_at||n.timestamp)}</small></span><i>›</i></button>)}{!shownNotes.length&&<p className="rf-empty">{loadingExtras?"Loading your notes…":notes.length?"No notes match your search.":"Your processed notes will appear here."}</p>}</div></Panel>
        <Panel cls="rf-heat-panel" icon="calendar" title="Study heat map" subtitle="Your activity across the last 12 weeks."><div className="rf-heatmap-wrap"><div className="rf-heat-days">{["Mon","Tue","Wed","Thu","Fri","Sat","Sun"].map(d=><span key={d}>{d}</span>)}</div><div className="rf-heat-grid">{(activity.length?activity:Array.from({length:84},()=>({level:0,label:"No activity recorded"}))).map((c,i)=><i key={i} className={"rf-heat-cell rf-heat-"+c.level} title={c.label}/>)}</div></div><div className="rf-heat-legend">LESS {[0,1,2,3,4].map(i=><i key={i} className={"rf-heat-cell rf-heat-"+i}/>)} MORE</div></Panel></div>
      <div className="rf-main-grid rf-lower-grid"><Panel cls="rf-subjects-panel" icon="chart" title="Your subjects" subtitle="Progress across your learning map." action="All subjects" onAction={()=>onNavigate("notes")}><div className="rf-subject-grid">{topics.slice(0,4).map(t=><button key={t.id} className="rf-subject-card" onClick={()=>onNavigate("notes")}><span className="rf-subject-heading"><ThreeIcon kind={t.id==="ds"?"target":"chart"} size={30}/><b>{t.name}</b></span><span className="rf-subject-track"><i className={t.color} style={{width:Math.max(0,Math.min(100,t.pct))+"%"}}/></span><small>{t.pct}% mastered</small></button>)}{!topics.length&&<p className="rf-empty">Topic mastery appears after your first quiz.</p>}</div></Panel>
        <Panel cls="rf-recommendations-panel" icon="bulb" title="AI recommendations" subtitle="Evidence-backed actions from your learning history." action="Refresh" onAction={onRefresh}><div className="rf-recommendation-list">{recommendations.map((r,i)=><article key={r.id} className="rf-recommendation-row"><button type="button" className="rf-recommendation" onClick={()=>startRecommendedAction(r)}><ThreeIcon kind={i===0?"target":r.action==="Practice Quiz"||r.action==="Reassessment"?"chart":"notes"} size={30}/><span><b>{r.title||("Recommended: "+r.action)}</b><small>{r.reason||"Suggested from your saved learning history."}</small><small className="rf-recommendation-evidence">{r.mastery_pct==null?"Planner evidence":("Estimated mastery "+r.mastery_pct+"%")+(r.attempts==null?"":" · "+r.attempts+" saved attempt(s)")} · {Math.round(Number(r.priority_score||0)*100)} priority</small>{r.evidence_confidence<0.4&&<small className="rf-recommendation-evidence">Evidence is limited; use this as a diagnostic check.</small>}</span><i>›</i></button><div className="rf-recommendation-controls"><button type="button" onClick={()=>practiceRecommendation(r)}>Practice & measure</button><button type="button" onClick={()=>markRecommendationComplete(r)}>Mark done</button><button type="button" onClick={()=>dismissRecommendationCard(r)}>Dismiss</button></div></article>)}{!recommendations.length&&<p className="rf-empty">{loadingExtras?"Refreshing your learner model…":(attempts.length?"No active recommendations. Your completed actions may be resolved.":"Complete a quiz to build a personalized learning profile.")}</p>}</div></Panel></div>
      <div className="rf-main-grid rf-analytics-grid"><Panel cls="rf-performance-panel" icon="chart" title="Quiz performance" subtitle={scores.length?"Saved quiz scores across your recent attempts.":"Your saved quiz scores will appear here."}><div className="rf-score-chart"><div className="rf-y-labels"><span>100</span><span>75</span><span>50</span><span>25</span><span>0</span></div><svg viewBox="0 0 660 155" preserveAspectRatio="none" aria-label="Saved quiz scores"><defs><linearGradient id="rfFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#64b6ac" stopOpacity=".38"/><stop offset="100%" stopColor="#119da4" stopOpacity="0"/></linearGradient></defs>{[8,43,78,113,148].map(y=><line key={y} x1="0" x2="660" y1={y} y2={y} className="rf-chart-gridline"/>)}{[0,94,188,282,376,470,564,659].map(x=><line key={x} x1={x} x2={x} y1="8" y2="148" className="rf-chart-gridline rf-vertical"/>)}{scores.length>1&&<><path d={area} fill="url(#rfFill)"/><path d={line} className="rf-score-line"/></>}{scores.map((p,i)=><circle key={i} cx={p.x} cy={p.y} r="4" className="rf-score-dot"><title>{p.title+": "+p.score+"%"}</title></circle>)}</svg></div><div className="rf-x-labels">{scores.map((s,i)=><span key={i} title={s.title}>Quiz {i+1}</span>)}</div></Panel>
        <Panel cls="rf-focus-panel" icon="pie" title="Study focus" subtitle="Where your learning activity is going."><div className="rf-focus-content"><div className="rf-focus-donut" style={{background:donut}}><div><b>{prettyMinutes(studyMins+Math.floor(liveStudySeconds/60))}</b><small>{activeStudySession?"tracked time · live":"recorded study time"}</small></div></div><div className="rf-focus-legend">{[["Quiz practice",focusCounts[0],"teal"],["Notes & uploads",focusCounts[1],"mint"],["Other activity",focusCounts[2],"peach"]].map(([label,val,tone])=><div className="rf-focus-row" key={label}><i className={tone}/><span>{label}</span><b>{focusTotal?Math.round(val/focusTotal*100):0}%</b></div>)}</div></div><footer className="rf-focus-foot"><Icon name="spark" size={14}/>{activeStudySession?(activeStudySession.status==="paused"?"Study session paused — paused time is excluded.":"Active session · "+liveStudyLabel+" tracked so far."):"Statistics use recorded active intervals, not page-open time."}</footer><div className="rf-study-controls"><button type="button" className="rf-link-button" disabled={studyBusy} onClick={async()=>{setStudyBusy(true);try{if(activeStudySession?.session_id){const result=await completeStudySession(activeStudySession.session_id);setActiveStudySession(null);const mins=Math.floor((Number(result?.session?.duration_seconds)||0)/60);toast?.("Study session saved: "+prettyMinutes(mins),"teal");if(onRefresh)await onRefresh();}else{const result=await startStudySession();setActiveStudySession(result?.session||null);toast?.(result?.already_active?"Restored your existing session.":"Study session started.","teal");}}catch(error){toast?.(error?.message||"Could not update study session.","coral");}finally{setStudyBusy(false);}}}>{studyBusy?"Saving…":activeStudySession?"Finish session":"Start study session"}</button>{activeStudySession?.status==="active"&&<button type="button" className="rf-link-button secondary" disabled={studyBusy} onClick={async()=>{setStudyBusy(true);try{const result=await pauseStudySession(activeStudySession.session_id);setActiveStudySession(result?.session||activeStudySession);toast?.("Timer paused. Your tracked time is saved.","teal");}catch(error){toast?.(error?.message||"Could not pause session.","coral");}finally{setStudyBusy(false);}}}>Pause</button>}{activeStudySession?.status==="paused"&&<button type="button" className="rf-link-button secondary" disabled={studyBusy} onClick={async()=>{setStudyBusy(true);try{const result=await resumeStudySession(activeStudySession.session_id);setActiveStudySession(result?.session||activeStudySession);toast?.("Timer resumed.","teal");}catch(error){toast?.(error?.message||"Could not resume session.","coral");}finally{setStudyBusy(false);}}}>Resume</button>}</div></Panel></div>
      <footer className="rf-footer">STUDYAI <span>·</span> Keep showing up. Your progress is adding up.</footer>
    </main>
  </div>;
}
