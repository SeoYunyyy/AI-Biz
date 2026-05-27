# ── 인증 Blueprint — 로그인/로그아웃/세션 관리 ──

import os
from functools import wraps
from flask import Blueprint, render_template, redirect, request, session, jsonify

auth_bp = Blueprint('auth', __name__)


def login_required(f):
    """미로그인 시 /login 으로 리디렉트하는 데코레이터"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


@auth_bp.route('/login')
def login_page():
    if 'user' in session:
        return redirect('/')
    return render_template(
        'login.html',
        supabase_url=os.getenv('SUPABASE_URL', ''),
        supabase_anon_key=os.getenv('SUPABASE_ANON_KEY', ''),
    )


@auth_bp.route('/auth/callback')
def auth_callback():
    # Supabase가 OAuth 완료 후 이 URL로 리디렉트 → 클라이언트 JS가 세션 처리
    return redirect('/')


@auth_bp.route('/api/auth/session', methods=['POST'])
def save_session():
    data = request.get_json()
    if not data or 'user' not in data:
        return jsonify({'error': '유저 정보 없음'}), 400
    user = data['user']
    session['user'] = {
        'id':     user.get('id'),
        'email':  user.get('email'),
        'name':   (user.get('user_metadata') or {}).get('full_name', ''),
        'avatar': (user.get('user_metadata') or {}).get('avatar_url', ''),
    }
    session['access_token'] = data.get('access_token', '')
    return jsonify({'status': 'ok', 'user': session['user']})


@auth_bp.route('/api/auth/user')
def get_current_user():
    if 'user' in session:
        return jsonify({'user': session['user']})
    return jsonify({'user': None}), 401


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'status': 'ok', 'redirect': '/login'})

# 로그인 페이지, OAuth 콜백, Flask 세션 저장/조회/삭제 엔드포인트
