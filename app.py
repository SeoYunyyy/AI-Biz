# ── Keepit 서버 진입점 ──

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from flask import Flask, render_template, jsonify

from database.db import init_db
from routes.archive import archive_bp
from routes.search import search_bp
from routes.reminder import reminder_bp
from routes.report import report_bp

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

# Blueprint 등록 (기능별 라우트 연결)
app.register_blueprint(archive_bp)
app.register_blueprint(search_bp)
app.register_blueprint(reminder_bp)
app.register_blueprint(report_bp)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/weekly-report')
def weekly_report_page():
    return render_template('report_weekly.html')


@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    init_db()
    app.run(debug=True)

# Flask 앱 초기화 및 기능별 Blueprint 등록, 서버 실행
