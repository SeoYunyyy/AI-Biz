// ── 로그인 페이지 — 이메일/비밀번호 인증 + Google OAuth + 배경 애니메이션 ──

(function () {
  'use strict';

  /* ── 1. Supabase 초기화 ── */
  const sb = window.supabase.createClient(
    window.__SUPABASE_URL__,
    window.__SUPABASE_ANON_KEY__
  );

  /* ── 2. 이미 로그인된 세션이면 바로 메인으로 ── */
  sb.auth.getSession().then(({ data: { session } }) => {
    if (session) pushSessionAndRedirect(session);
  });

  sb.auth.onAuthStateChange((_event, session) => {
    if (session) pushSessionAndRedirect(session);
  });

  async function pushSessionAndRedirect(session) {
    try {
      await fetch('/api/auth/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user: session.user, access_token: session.access_token }),
      });
    } catch (_) {}
    window.location.href = '/';
  }

  /* ── 3. DOM 요소 ── */
  const tabLogin      = document.getElementById('tab-login');
  const tabSignup     = document.getElementById('tab-signup');
  const confirmGroup  = document.getElementById('confirm-group');
  const emailInput    = document.getElementById('email-input');
  const passwordInput = document.getElementById('password-input');
  const confirmInput  = document.getElementById('confirm-input');
  const emailBtn      = document.getElementById('email-submit-btn');
  const emailBtnText  = emailBtn.querySelector('.email-btn-text');
  const googleBtn     = document.getElementById('google-login-btn');
  const msgBox        = document.getElementById('auth-message');
  const footerText    = document.getElementById('footer-text');
  const switchBtn     = document.getElementById('switch-to-signup');

  /* ── 4. 탭 토글 (로그인 ↔ 회원가입) ── */
  let mode = 'login'; // 'login' | 'signup'

  function setMode(m) {
    mode = m;
    clearMessage();
    [emailInput, passwordInput, confirmInput].forEach(el => el.classList.remove('error'));

    if (mode === 'login') {
      tabLogin.classList.add('active');    tabLogin.setAttribute('aria-selected', 'true');
      tabSignup.classList.remove('active'); tabSignup.setAttribute('aria-selected', 'false');
      confirmGroup.style.display = 'none';
      emailBtnText.textContent   = '로그인하기';
      passwordInput.autocomplete = 'current-password';
      footerText.innerHTML       = '계정이 없으신가요? <button class="switch-mode-btn" id="switch-to-signup">회원가입</button>';
    } else {
      tabSignup.classList.add('active');    tabSignup.setAttribute('aria-selected', 'true');
      tabLogin.classList.remove('active');  tabLogin.setAttribute('aria-selected', 'false');
      confirmGroup.style.display = 'block';
      emailBtnText.textContent   = '회원가입하기';
      passwordInput.autocomplete = 'new-password';
      footerText.innerHTML       = '이미 계정이 있으신가요? <button class="switch-mode-btn" id="switch-to-signup">로그인</button>';
    }

    // 동적으로 재생성된 버튼에 이벤트 재연결
    document.getElementById('switch-to-signup')?.addEventListener('click', () => {
      setMode(mode === 'login' ? 'signup' : 'login');
    });
  }

  tabLogin.addEventListener('click',  () => setMode('login'));
  tabSignup.addEventListener('click', () => setMode('signup'));
  switchBtn?.addEventListener('click', () => setMode('signup'));

  /* ── 5. 메시지 표시 헬퍼 ── */
  function showError(msg) {
    msgBox.textContent = msg;
    msgBox.className   = 'auth-message is-error';
  }

  function showSuccess(msg) {
    msgBox.textContent = msg;
    msgBox.className   = 'auth-message is-success';
  }

  function clearMessage() {
    msgBox.textContent = '';
    msgBox.className   = 'auth-message';
  }

  /* ── 6. 이메일/비밀번호 인증 ── */
  function setEmailLoading(on) {
    emailBtn.disabled = on;
    emailBtn.classList.toggle('loading', on);
    googleBtn.disabled = on;
  }

  emailBtn.addEventListener('click', async () => {
    clearMessage();
    const email    = emailInput.value.trim();
    const password = passwordInput.value;
    const confirm  = confirmInput.value;

    /* 기본 유효성 */
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      emailInput.classList.add('error');
      return showError('올바른 이메일 주소를 입력해주세요.');
    }
    if (password.length < 6) {
      passwordInput.classList.add('error');
      return showError('비밀번호는 6자 이상이어야 합니다.');
    }
    if (mode === 'signup' && password !== confirm) {
      confirmInput.classList.add('error');
      return showError('비밀번호가 일치하지 않습니다.');
    }

    setEmailLoading(true);

    try {
      if (mode === 'login') {
        const { error } = await sb.auth.signInWithPassword({ email, password });
        if (error) {
          if (error.message.includes('Invalid login credentials')) {
            showError('이메일 또는 비밀번호가 올바르지 않습니다.');
          } else if (error.message.includes('Email not confirmed')) {
            showError('이메일 인증이 필요합니다. 받은편지함을 확인해주세요.');
          } else {
            showError(error.message);
          }
          setEmailLoading(false);
        }
        // 성공 시 onAuthStateChange → pushSessionAndRedirect

      } else {
        const { data, error } = await sb.auth.signUp({ email, password });
        if (error) {
          if (error.message.includes('already registered')) {
            showError('이미 가입된 이메일입니다. 로그인을 시도해주세요.');
          } else {
            showError(error.message);
          }
          setEmailLoading(false);
        } else if (data.user && !data.session) {
          // 이메일 확인이 필요한 경우
          showSuccess('가입 확인 이메일을 발송했습니다. 받은편지함을 확인하고 링크를 클릭해주세요.');
          setEmailLoading(false);
        }
        // 이메일 확인 없이 자동 로그인되면 onAuthStateChange가 처리
      }
    } catch (e) {
      showError('오류가 발생했습니다. 잠시 후 다시 시도해주세요.');
      setEmailLoading(false);
    }
  });

  /* Enter 키 지원 */
  [emailInput, passwordInput, confirmInput].forEach(el => {
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter') emailBtn.click();
    });
  });

  /* ── 7. Google OAuth — 무한 로딩 방지 포함 ── */
  let googleLoadingTimer = null;

  function setGoogleLoading(on) {
    googleBtn.classList.toggle('loading', on);
    googleBtn.disabled = on;
    emailBtn.disabled  = on;
  }

  function resetGoogleBtn() {
    setGoogleLoading(false);
    clearTimeout(googleLoadingTimer);
    googleLoadingTimer = null;
  }

  // 사용자가 OAuth 창을 닫고 이 페이지로 돌아오면 버튼 초기화
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && googleBtn.classList.contains('loading')) {
      // 세션이 없으면 로딩 해제
      sb.auth.getSession().then(({ data: { session } }) => {
        if (!session) resetGoogleBtn();
      });
    }
  });

  // 페이지 포커스로도 감지 (일부 브라우저 대비)
  window.addEventListener('focus', () => {
    if (googleBtn.classList.contains('loading')) {
      sb.auth.getSession().then(({ data: { session } }) => {
        if (!session) resetGoogleBtn();
      });
    }
  });

  googleBtn.addEventListener('click', async () => {
    clearMessage();
    setGoogleLoading(true);

    // 15초 뒤 자동 해제 (리다이렉트가 일어나지 않는 경우 대비)
    googleLoadingTimer = setTimeout(() => {
      resetGoogleBtn();
      showError('Google 로그인 시간이 초과됐습니다. 다시 시도해주세요.');
    }, 15000);

    const { error } = await sb.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });

    if (error) {
      resetGoogleBtn();
      showError('Google 로그인 중 오류가 발생했습니다. 다시 시도해주세요.');
    }
    // 성공이면 페이지가 Google로 리다이렉트됨 → 로딩 상태 그대로 유지
  });

  /* ── 8. 캔버스 골든 블롭 배경 ── */
  const canvas = document.getElementById('bg-canvas');
  const ctx    = canvas.getContext('2d');
  let W, H;
  const mouse = { x: 0, y: 0 };
  let mx = 0, my = 0;

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);
  window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; }, { passive: true });

  const blobs = [
    { cx: 0.75, cy: 0.3,  r: 0.38, color: [180, 120, 30],  speed: 0.00018, phase: 0 },
    { cx: 0.55, cy: 0.65, r: 0.28, color: [140, 90,  15],  speed: 0.00025, phase: 2.1 },
    { cx: 0.85, cy: 0.75, r: 0.22, color: [220, 170, 60],  speed: 0.0002,  phase: 4.3 },
    { cx: 0.65, cy: 0.15, r: 0.18, color: [100, 65,  10],  speed: 0.0003,  phase: 1.0 },
    { cx: 0.4,  cy: 0.5,  r: 0.15, color: [200, 150, 50],  speed: 0.00022, phase: 3.5 },
  ];

  function draw(ts) {
    ctx.clearRect(0, 0, W, H);
    mx += ((mouse.x / W - 0.5) * 0.05 - mx) * 0.04;
    my += ((mouse.y / H - 0.5) * 0.05 - my) * 0.04;

    ctx.fillStyle = '#0A0A0A';
    ctx.fillRect(0, 0, W, H);

    blobs.forEach(b => {
      const t = ts * b.speed + b.phase;
      const x = (b.cx + Math.sin(t * 1.3) * 0.08 + mx) * W;
      const y = (b.cy + Math.cos(t * 1.1) * 0.06 + my) * H;
      const r = b.r * Math.min(W, H) * (0.9 + Math.sin(t * 0.7) * 0.1);
      const [red, grn, blu] = b.color;

      const grd = ctx.createRadialGradient(x, y, 0, x, y, r);
      grd.addColorStop(0,   `rgba(${red},${grn},${blu},0.28)`);
      grd.addColorStop(0.5, `rgba(${red},${grn},${blu},0.10)`);
      grd.addColorStop(1,   `rgba(${red},${grn},${blu},0)`);

      ctx.beginPath();
      ctx.ellipse(x, y,
        r * (1 + Math.sin(t * 0.9) * 0.15),
        r * (1 + Math.cos(t * 1.2) * 0.15),
        t * 0.3, 0, Math.PI * 2);
      ctx.fillStyle = grd;
      ctx.fill();
    });

    const ag = ctx.createRadialGradient(
      (0.65 + mx) * W, (0.4 + my) * H, 0,
      (0.65 + mx) * W, (0.4 + my) * H, Math.min(W, H) * 0.55
    );
    ag.addColorStop(0,   'rgba(160,100,20,0.08)');
    ag.addColorStop(0.6, 'rgba(80,50,10,0.04)');
    ag.addColorStop(1,   'rgba(0,0,0,0)');
    ctx.fillStyle = ag;
    ctx.fillRect(0, 0, W, H);

    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);

  /* ── 9. GSAP 시네마틱 페이드인 ── */
  window.addEventListener('load', () => {
    if (!window.gsap) return;
    gsap.timeline({ defaults: { ease: 'power3.out' } })
      .to('.login-nav',          { opacity: 1, y: 0,           duration: 0.9 })
      .to('.brand-eyebrow',      { opacity: 1, y: 0,           duration: 0.8 }, '-=0.5')
      .to('.brand-title',        { opacity: 1, y: 0,           duration: 0.9 }, '-=0.5')
      .to('.brand-description',  { opacity: 1, y: 0,           duration: 0.8 }, '-=0.5')
      .to('.login-card-wrapper', { opacity: 1, y: 0, scale: 1, duration: 1.0, ease: 'power2.out' }, '-=0.8')
      .set('.brand-section',     { opacity: 1 }, 0);
  });

  /* ── 10. Google 버튼 마그네틱 호버 ── */
  googleBtn.addEventListener('mousemove', e => {
    if (googleBtn.disabled) return;
    const r  = googleBtn.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width  / 2);
    const dy = e.clientY - (r.top  + r.height / 2);
    googleBtn.style.transform = `translateY(-2px) translate(${dx * 0.07}px,${dy * 0.07}px) scale(1.01)`;
  });
  googleBtn.addEventListener('mouseleave', () => { googleBtn.style.transform = ''; });

})();

// 이메일 로그인/회원가입, Google OAuth(무한 로딩 방지), 골든 블롭 배경, GSAP 페이드인
