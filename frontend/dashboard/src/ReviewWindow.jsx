import React,{useEffect,useRef} from 'react'
import {createPortal} from 'react-dom'

export default function ReviewWindow({children,onClose,onExit,viewKey,title}) {
  const dialog=useRef(null)
  const scrollPositions=useRef(new Map())
  useEffect(()=>{
    const previous=document.activeElement,overflow=document.body.style.overflow
    dialog.current.showModal();document.body.style.overflow='hidden'
    return()=>{document.body.style.overflow=overflow;previous?.focus()}
  },[])
  useEffect(()=>{dialog.current.scrollTop=scrollPositions.current.get(viewKey)||0},[viewKey])
  return createPortal(<dialog ref={dialog} className="review-window" aria-label={title||'Complaint review'} onScroll={()=>scrollPositions.current.set(viewKey,dialog.current.scrollTop)} onCancel={e=>{e.preventDefault();onClose()}}><div className="review-window-header"><b>{title||(viewKey?'Complaint details':'Complaint review')}</b><div className="btnrow">{viewKey&&<button autoFocus className="ghost" onClick={onClose}>Close complaint · Back to list</button>}<button autoFocus={!viewKey} className="ghost" onClick={onExit} aria-label="Close review and return to dashboard">Close review ×</button></div></div><div className="review-window-body">{children}</div></dialog>,document.body)
}
