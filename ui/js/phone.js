// ============================================================= phone access settings (computer only)
function loadQr(){return new Promise((ok,fail)=>{if(window.qrcode)return ok();const s=document.createElement("script");s.src="/static/qrcode.min.js";s.onload=ok;s.onerror=fail;document.head.appendChild(s)})}
async function drawPhone(st){
  $("#phoneon").checked=st.enabled&&st.running;$("#phonebox").hidden=!(st.enabled&&st.running);
  if(!(st.enabled&&st.running))return;
  $("#phoneurl").textContent=st.url;$("#phonepin").textContent=st.pin;
  $("#phonenote").innerHTML=`Your computer must be on with jobslop open, and both on the same Wi-Fi. ${st.phones?`<b>${st.phones}</b> phone${st.phones>1?"s":""} signed in.`:""} If Windows asks about the firewall, tick <b>Private networks</b> and allow.`+
    (st.ip==="127.0.0.1"?' <span style="color:var(--warn)">This computer doesn\'t seem to be on a network right now.</span>':"");
  try{await loadQr();const q=qrcode(0,"M");q.addData(st.url);q.make();$("#phoneqr").innerHTML=q.createSvgTag({cellSize:4,margin:2})}catch(e){$("#phoneqr").textContent=""}
}
async function loadPhone(){try{drawPhone(await get("/api/phone"))}catch(e){}}
$("#phoneon").onchange=async()=>{const r=await post("/api/phone",{enabled:$("#phoneon").checked});
  if(r.error)toast(r.error);else toast(r.enabled?"Phone access on — scan the code with your phone":"Phone access off");drawPhone(r)};
$("#phonenewpin").onclick=async()=>{const r=await post("/api/phone",{new_pin:true});drawPhone(r);toast("New PIN made — phones need to sign in again")};
$("#phonesignout").onclick=async()=>{const r=await post("/api/phone",{signout:true});drawPhone(r);toast("All phones signed out")};

const hideSplash=()=>$("#splash").classList.add("gone");
setTimeout(hideSplash,6000);   // never leave the splash up if something is slow
