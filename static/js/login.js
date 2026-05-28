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

  /* ── 8. 캔버스 배경 — 3레이어 시네마틱 앰비언트 ── */
  const canvas = document.getElementById('bg-canvas');
  const ctx    = canvas.getContext('2d');
  let W, H;
  const mouse = { x: -9999, y: -9999 };

  // 레이어별 마우스 보간값 (느림→빠름 순)
  const lerpX = [0, 0, 0];
  const lerpY = [0, 0, 0];
  const lerpSpeed = [0.028, 0.058, 0.110];

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);
  window.addEventListener('mousemove', e => { mouse.x = e.clientX; mouse.y = e.clientY; }, { passive: true });

  // ── 레이어 0: 원거리 앰비언트 (광범위·어두운 에스프레소 톤) ──
  const layer0 = [
    { cx: 0.72, cy: 0.27, r: 0.52, color: [152, 96, 20],  speed: 0.00010, phase: 0.0, alpha: 0.62, px: 0.08 },
    { cx: 0.46, cy: 0.68, r: 0.44, color: [ 92, 55, 10],  speed: 0.00014, phase: 2.7, alpha: 0.52, px: 0.06 },
    { cx: 0.88, cy: 0.50, r: 0.36, color: [168, 115, 35], speed: 0.00012, phase: 5.0, alpha: 0.58, px: 0.07 },
    { cx: 0.26, cy: 0.20, r: 0.30, color: [ 72, 40,  6],  speed: 0.00018, phase: 1.2, alpha: 0.42, px: 0.05 },
  ];

  // ── 레이어 1: 중간 글로우 (골드·브론즈 톤) ──
  const layer1 = [
    { cx: 0.68, cy: 0.33, r: 0.25, color: [212, 158, 50], speed: 0.00026, phase: 0.4, alpha: 0.90, px: 0.16 },
    { cx: 0.78, cy: 0.57, r: 0.21, color: [192, 132, 36], speed: 0.00030, phase: 3.0, alpha: 0.85, px: 0.18 },
    { cx: 0.53, cy: 0.45, r: 0.17, color: [232, 182, 72], speed: 0.00033, phase: 1.6, alpha: 0.78, px: 0.20 },
    { cx: 0.39, cy: 0.59, r: 0.13, color: [152, 102, 26], speed: 0.00037, phase: 4.3, alpha: 0.72, px: 0.13 },
    { cx: 0.91, cy: 0.17, r: 0.12, color: [182, 135, 46], speed: 0.00041, phase: 1.9, alpha: 0.65, px: 0.22 },
  ];

  // ── 레이어 2: 핀포인트 하이라이트 (작고 밝음, 강한 패럴랙스) ──
  const layer2 = [
    { cx: 0.70, cy: 0.28, r: 0.068, color: [250, 215, 95], speed: 0.00056, phase: 0.2, alpha: 1.0, px: 0.32 },
    { cx: 0.73, cy: 0.43, r: 0.052, color: [230, 185, 76], speed: 0.00066, phase: 2.3, alpha: 1.0, px: 0.38 },
    { cx: 0.60, cy: 0.23, r: 0.042, color: [240, 202, 88], speed: 0.00050, phase: 3.8, alpha: 0.92, px: 0.29 },
  ];

  function drawBlob(b, ts, ix, iy) {
    const t      = ts * b.speed + b.phase;
    const orgX   = Math.sin(t * 1.3) * 0.07 + Math.cos(t * 0.72) * 0.03;
    const orgY   = Math.cos(t * 1.1) * 0.05 + Math.sin(t * 0.88) * 0.03;
    const x      = (b.cx + orgX + ix * b.px) * W;
    const y      = (b.cy + orgY + iy * b.px) * H;
    const pulse  = 0.90 + Math.sin(t * 0.78 + b.phase) * 0.10;
    const r      = b.r * Math.min(W, H) * pulse;
    const [R, G, B] = b.color;
    const ratioX = 1 + Math.sin(t * 0.84) * 0.20;
    const ratioY = 1 + Math.cos(t * 1.14) * 0.20;

    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(t * 0.22);
    ctx.scale(ratioX, ratioY);

    const grd = ctx.createRadialGradient(0, 0, 0, 0, 0, r);
    grd.addColorStop(0,    `rgba(${R},${G},${B},${0.30 * b.alpha})`);
    grd.addColorStop(0.38, `rgba(${R},${G},${B},${0.13 * b.alpha})`);
    grd.addColorStop(0.72, `rgba(${R},${G},${B},${0.04 * b.alpha})`);
    grd.addColorStop(1,    `rgba(${R},${G},${B},0)`);

    ctx.beginPath();
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.fillStyle = grd;
    ctx.fill();
    ctx.restore();
  }

  function draw(ts) {
    ctx.clearRect(0, 0, W, H);

    // 마우스 노말라이즈 & 레이어별 보간
    const nx = mouse.x / W - 0.5;
    const ny = mouse.y / H - 0.5;
    for (let i = 0; i < 3; i++) {
      lerpX[i] += (nx - lerpX[i]) * lerpSpeed[i];
      lerpY[i] += (ny - lerpY[i]) * lerpSpeed[i];
    }

    // 베이스 배경
    ctx.fillStyle = '#0A0A0A';
    ctx.fillRect(0, 0, W, H);

    // 레이어 0 — 원거리 앰비언트
    layer0.forEach(b => drawBlob(b, ts, lerpX[0], lerpY[0]));

    // 메인 블룸 — 중앙 우측, 천천히 호흡
    const bt = ts * 0.000092;
    const bx = (0.65 + Math.sin(bt * 1.1) * 0.052 + lerpX[0] * 0.55) * W;
    const by = (0.38 + Math.cos(bt * 0.88) * 0.042 + lerpY[0] * 0.55) * H;
    const br = Math.min(W, H) * (0.60 + Math.sin(bt * 1.35) * 0.032);
    const bloom = ctx.createRadialGradient(bx, by, 0, bx, by, br);
    bloom.addColorStop(0,    'rgba(172,112,30,0.14)');
    bloom.addColorStop(0.28, 'rgba(130,82,16,0.08)');
    bloom.addColorStop(0.60, 'rgba(72,42,8,0.03)');
    bloom.addColorStop(1,    'rgba(0,0,0,0)');
    ctx.fillStyle = bloom;
    ctx.fillRect(0, 0, W, H);

    // 레이어 1 — 중간 글로우
    layer1.forEach(b => drawBlob(b, ts, lerpX[1], lerpY[1]));

    // 레이어 2 — 핀포인트 하이라이트
    layer2.forEach(b => drawBlob(b, ts, lerpX[2], lerpY[2]));

    // 커서 글로우 — 마우스 위치에 따라 즉각 반응
    if (mouse.x > 0) {
      const cg = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, Math.min(W, H) * 0.13);
      cg.addColorStop(0,   'rgba(208,158,48,0.11)');
      cg.addColorStop(0.5, 'rgba(148,98,22,0.04)');
      cg.addColorStop(1,   'rgba(0,0,0,0)');
      ctx.fillStyle = cg;
      ctx.fillRect(0, 0, W, H);
    }

    // 비네트 — 가장자리 어둠
    const vg = ctx.createRadialGradient(W * 0.5, H * 0.44, Math.min(W, H) * 0.22, W * 0.5, H * 0.44, Math.min(W, H) * 0.98);
    vg.addColorStop(0, 'rgba(0,0,0,0)');
    vg.addColorStop(1, 'rgba(0,0,0,0.72)');
    ctx.fillStyle = vg;
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
