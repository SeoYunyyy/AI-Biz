// ── 로그인 페이지 — 배경 애니메이션 + Supabase Google OAuth ──

(function () {
  'use strict';

  /* ── CDN 실패 시 요소 강제 표시 (폴백) ── */
  function showAllElements() {
    const targets = ['.login-nav', '.brand-section', '.brand-eyebrow',
                     '.brand-title', '.brand-description', '.login-card-wrapper'];
    targets.forEach(sel => {
      const el = document.querySelector(sel);
      if (el) { el.style.opacity = '1'; el.style.transform = 'none'; }
    });
  }

  /* ── 1. Supabase 초기화 ── */
  const SUPABASE_URL      = window.__SUPABASE_URL__;
  const SUPABASE_ANON_KEY = window.__SUPABASE_ANON_KEY__;

  /* Supabase CDN 로딩 실패 시 화면이 검게 남지 않도록 guard */
  if (!window.supabase) {
    console.error('[Keepit] Supabase SDK 로딩 실패 — CDN 연결을 확인하세요.');
    window.addEventListener('load', showAllElements);
    return;
  }

  const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

  /* ── 2. 이미 로그인된 세션 확인 → 메인으로 이동 ── */
  sb.auth.getSession().then(({ data: { session } }) => {
    if (session) pushSessionAndRedirect(session);
  });

  sb.auth.onAuthStateChange(async (_event, session) => {
    if (session) await pushSessionAndRedirect(session);
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

  /* ── 3. Google 로그인 버튼 ── */
  const googleBtn = document.getElementById('google-login-btn');
  const errMsg    = document.getElementById('error-message');

  if (googleBtn) {
    googleBtn.addEventListener('click', async () => {
      googleBtn.classList.add('loading');
      googleBtn.disabled = true;
      errMsg.style.display = 'none';

      const redirectTo = `${window.location.origin}/auth/callback`;
      const { error } = await sb.auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo },
      });

      if (error) {
        googleBtn.classList.remove('loading');
        googleBtn.disabled = false;
        errMsg.textContent = '로그인 중 오류가 발생했습니다. 다시 시도해주세요.';
        errMsg.style.display = 'block';
      }
    });
  }

  /* ── 4. 캔버스 배경 — 유기적 골든 블롭 애니메이션 ── */
  const canvas = document.getElementById('bg-canvas');
  const ctx    = canvas.getContext('2d');

  let W, H, mouse = { x: 0, y: 0 }, rafId;

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  window.addEventListener('mousemove', e => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
  }, { passive: true });

  /* 블롭 파라미터 */
  const blobs = [
    { cx: 0.75, cy: 0.3,  r: 0.38, color: [180, 120, 30],  speed: 0.00018, phase: 0 },
    { cx: 0.55, cy: 0.65, r: 0.28, color: [140, 90,  15],   speed: 0.00025, phase: 2.1 },
    { cx: 0.85, cy: 0.75, r: 0.22, color: [220, 170, 60],   speed: 0.0002,  phase: 4.3 },
    { cx: 0.65, cy: 0.15, r: 0.18, color: [100, 65,  10],   speed: 0.00030, phase: 1.0 },
    { cx: 0.4,  cy: 0.5,  r: 0.15, color: [200, 150, 50],   speed: 0.00022, phase: 3.5 },
  ];

  /* 마우스 오프셋 (관성) */
  let mx = 0, my = 0;

  function draw(ts) {
    ctx.clearRect(0, 0, W, H);

    /* 부드러운 마우스 추적 */
    mx += ((mouse.x / W - 0.5) * 0.05 - mx) * 0.04;
    my += ((mouse.y / H - 0.5) * 0.05 - my) * 0.04;

    /* 짙은 배경 */
    ctx.fillStyle = '#0A0A0A';
    ctx.fillRect(0, 0, W, H);

    blobs.forEach(b => {
      const t    = ts * b.speed + b.phase;
      const x    = (b.cx + Math.sin(t * 1.3) * 0.08 + mx) * W;
      const y    = (b.cy + Math.cos(t * 1.1) * 0.06 + my) * H;
      const r    = b.r * Math.min(W, H) * (0.9 + Math.sin(t * 0.7) * 0.1);
      const [red, grn, blu] = b.color;

      const grd = ctx.createRadialGradient(x, y, 0, x, y, r);
      grd.addColorStop(0,   `rgba(${red},${grn},${blu},0.28)`);
      grd.addColorStop(0.5, `rgba(${red},${grn},${blu},0.10)`);
      grd.addColorStop(1,   `rgba(${red},${grn},${blu},0)`);

      ctx.beginPath();
      ctx.ellipse(
        x, y,
        r * (1 + Math.sin(t * 0.9) * 0.15),
        r * (1 + Math.cos(t * 1.2) * 0.15),
        t * 0.3,
        0, Math.PI * 2,
      );
      ctx.fillStyle = grd;
      ctx.fill();
    });

    /* 중앙 앰비언트 글로우 */
    const cx = (0.65 + mx) * W;
    const cy = (0.4  + my) * H;
    const ag = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.min(W, H) * 0.55);
    ag.addColorStop(0,   'rgba(160,100,20,0.08)');
    ag.addColorStop(0.6, 'rgba(80, 50, 10, 0.04)');
    ag.addColorStop(1,   'rgba(0,  0,  0, 0)');
    ctx.fillStyle = ag;
    ctx.fillRect(0, 0, W, H);

    rafId = requestAnimationFrame(draw);
  }

  rafId = requestAnimationFrame(draw);

  /* ── 5. GSAP 시네마틱 페이드인 (GSAP 없으면 즉시 표시) ── */
  window.addEventListener('load', () => {
    if (!window.gsap) {
      /* GSAP CDN 실패 시 요소 즉시 표시 */
      showAllElements();
      return;
    }

    const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });

    tl
      .to('.login-nav',         { opacity: 1, y: 0,          duration: 0.9 })
      .to('.brand-eyebrow',     { opacity: 1, y: 0,          duration: 0.8 }, '-=0.5')
      .to('.brand-title',       { opacity: 1, y: 0,          duration: 0.9 }, '-=0.5')
      .to('.brand-description', { opacity: 1, y: 0,          duration: 0.8 }, '-=0.5')
      .to('.login-card-wrapper',{ opacity: 1, y: 0, scale: 1, duration: 1.0,
                                   ease: 'power2.out' }, '-=0.8')
      .set('.brand-section',    { opacity: 1 }, 0);
  });

  /* ── 6. 카드 마그네틱 호버 (버튼) ── */
  const btn = document.getElementById('google-login-btn');
  if (btn) {
    btn.addEventListener('mousemove', e => {
      const r   = btn.getBoundingClientRect();
      const dx  = e.clientX - (r.left + r.width  / 2);
      const dy  = e.clientY - (r.top  + r.height / 2);
      btn.style.transform = `translateY(-2px) translate(${dx * 0.07}px, ${dy * 0.07}px) scale(1.01)`;
    });
    btn.addEventListener('mouseleave', () => {
      btn.style.transform = '';
    });
  }
})();

// Supabase Google OAuth 로그인, 캔버스 골든 블롭 배경, GSAP 등장 애니메이션
