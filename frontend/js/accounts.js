"use strict";
(() => {
  const $ = (s) => document.querySelector(s);
  const cfg = window.SoundScopeAccountsConfig;
  const modal = $("#account-modal"), entry = $("#account-entry"), status = $("#account-status");
  if (!modal || !entry || !cfg) return;
  const endpoint = `https://cognito-idp.${cfg.region}.amazonaws.com/`;
  const tabs = [...modal.querySelectorAll("[data-account-tab]")], login = $("#account-login-form"), signup = $("#account-signup-form");
  const confirmBox = $("#account-confirm"), confirmForm = $("#account-confirm-form");
  let pendingEmail = "";
  const sessionKey = "soundscope_account_session";
  const api = async (target, body) => {
    const r = await fetch(endpoint,{method:"POST",headers:{"Content-Type":"application/x-amz-json-1.1","X-Amz-Target":`AWSCognitoIdentityProviderService.${target}`},body:JSON.stringify(body)});
    const data = await r.json().catch(()=>({}));
    if(!r.ok){const e=new Error(data.message||data.__type||"COGNITO_ERROR");e.code=(data.__type||"").split("#").pop();throw e} return data;
  };
  const messageFor = (e) => ({
    UsernameExistsException:"Este e-mail já possui uma conta SoundScope.",
    UserNotConfirmedException:"Sua conta ainda precisa ser confirmada pelo código enviado ao e-mail.",
    NotAuthorizedException:"E-mail ou senha incorretos.",
    CodeMismatchException:"Código de confirmação incorreto.",
    ExpiredCodeException:"Esse código expirou. Solicite um novo código.",
    InvalidPasswordException:"A senha não atende aos requisitos de segurança.",
    LimitExceededException:"Muitas tentativas. Aguarde um pouco e tente novamente."
  }[e.code] || e.message || "Não foi possível concluir. Tente novamente.");
  const setTab=(name)=>{tabs.forEach(b=>b.classList.toggle("is-active",b.dataset.accountTab===name));login?.classList.toggle("is-hidden",name!=="login");signup?.classList.toggle("is-hidden",name!=="signup");confirmBox?.classList.add("is-hidden");if(status)status.textContent=""};
  const open=()=>{document.documentElement.classList.add("account-open");modal.classList.remove("is-hidden");document.documentElement.style.overflow="hidden";requestAnimationFrame(()=>modal.querySelector("input")?.focus({preventScroll:true}))};
  const close=()=>{modal.classList.add("is-hidden");document.documentElement.classList.remove("account-open");document.documentElement.style.overflow="";entry.focus({preventScroll:true})};
  const decodeJwt=(token)=>{try{return JSON.parse(decodeURIComponent(atob(token.split(".")[1].replace(/-/g,"+").replace(/_/g,"/")).split("").map(c=>"%"+("00"+c.charCodeAt(0).toString(16)).slice(-2)).join("")))}catch(_){return{}}};
  const renderSession=(session)=>{const guest=$(".account-entry__guest"),user=$(".account-entry__user"),name=$("#account-name"),avatar=$("#account-avatar");if(!session){guest?.classList.remove("is-hidden");user?.classList.add("is-hidden");return}const claims=decodeJwt(session.idToken),display=claims.name||claims["cognito:username"]||claims.email||"Minha conta";guest?.classList.add("is-hidden");user?.classList.remove("is-hidden");if(name)name.textContent=display;if(avatar)avatar.textContent=display.split(/\s+/).slice(0,2).map(x=>x[0]).join("").toUpperCase()};
  entry.addEventListener("click",open);modal.querySelectorAll("[data-account-close]").forEach(el=>el.addEventListener("click",close));tabs.forEach(b=>b.addEventListener("click",()=>setTab(b.dataset.accountTab)));document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!modal.classList.contains("is-hidden"))close()});
  signup?.addEventListener("submit",async(e)=>{e.preventDefault();if(!signup.reportValidity())return;const d=new FormData(signup);pendingEmail=String(d.get("email")).trim().toLowerCase();status.textContent="Criando sua conta…";try{await api("SignUp",{ClientId:cfg.clientId,Username:pendingEmail,Password:String(d.get("password")),UserAttributes:[{Name:"email",Value:pendingEmail},{Name:"name",Value:String(d.get("name")).trim()},{Name:"preferred_username",Value:String(d.get("username")).replace(/^@/,"").trim()}]});signup.classList.add("is-hidden");tabs.forEach(b=>b.classList.remove("is-active"));confirmBox.classList.remove("is-hidden");status.textContent="Código enviado. Confira seu e-mail."}catch(err){status.textContent=messageFor(err)}});
  confirmForm?.addEventListener("submit",async(e)=>{e.preventDefault();if(!confirmForm.reportValidity())return;status.textContent="Confirmando…";try{await api("ConfirmSignUp",{ClientId:cfg.clientId,Username:pendingEmail,ConfirmationCode:String(new FormData(confirmForm).get("code")).trim()});setTab("login");login.querySelector('[name="email"]').value=pendingEmail;status.textContent="Conta confirmada. Agora faça seu primeiro login."}catch(err){status.textContent=messageFor(err)}});
  login?.addEventListener("submit",async(e)=>{e.preventDefault();if(!login.reportValidity())return;const d=new FormData(login),email=String(d.get("email")).trim().toLowerCase();status.textContent="Entrando…";try{const data=await api("InitiateAuth",{AuthFlow:"USER_PASSWORD_AUTH",ClientId:cfg.clientId,AuthParameters:{USERNAME:email,PASSWORD:String(d.get("password"))}});const a=data.AuthenticationResult;if(!a?.IdToken)throw new Error("Sessão não recebida.");const session={idToken:a.IdToken,accessToken:a.AccessToken,refreshToken:a.RefreshToken,expiresAt:Date.now()+Number(a.ExpiresIn||3600)*1000};sessionStorage.setItem(sessionKey,JSON.stringify(session));renderSession(session);status.textContent="Bem-vindo ao SoundScope.";setTimeout(close,450)}catch(err){if(err.code==="UserNotConfirmedException"){pendingEmail=email;login.classList.add("is-hidden");tabs.forEach(b=>b.classList.remove("is-active"));confirmBox.classList.remove("is-hidden")}status.textContent=messageFor(err)}});
  modal.querySelectorAll("[data-account-provider]").forEach(button=>button.addEventListener("click",()=>{status.textContent=`${button.dataset.accountProvider}: vamos ativar este provedor na próxima etapa.`}));
  let stored=null;try{stored=JSON.parse(sessionStorage.getItem(sessionKey)||"null")}catch(_){}if(stored?.expiresAt>Date.now())renderSession(stored);else sessionStorage.removeItem(sessionKey);
})();