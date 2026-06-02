// ── Keepit 메인 인터랙션 ──

const DEFAULT_USER_ID = '00000000-0000-0000-0000-000000000001'

// 채팅 세션 상태 (패널 열릴 때 초기화)
let chatHistory = []
let shownIds = new Set()

const promptInput = document.getElementById('prompt-input')
const submitBtn   = document.getElementById('submit-btn')
const resultsDiv  = document.getElementById('results')
const modal       = document.getElementById('modal')
const modalBody   = document.getElementById('modal-body')
const rightPanel  = document.getElementById('right-panel')
const panelBody   = document.getElementById('panel-body')
const panelTitle  = document.getElementById('panel-title')

// URL 여부 판별
function isURL(str) {
    return /^https?:\/\//i.test(str) || /^www\./i.test(str)
}

// 입력에서 URL과 마감기한 분리
function parseInput(text) {
    const deadlineMatch = text.match(/마감[：:]\s*(\d{4}-\d{2}-\d{2})/)
    const deadline = deadlineMatch ? deadlineMatch[1] : null
    const url = text.replace(/마감[：:]\s*\d{4}-\d{2}-\d{2}/, '').trim()
    return { url, deadline }
}

function showResults(html) {
    resultsDiv.innerHTML = html
    resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

function setLoading(on) {
    submitBtn.disabled = on
    submitBtn.innerHTML = on ? '&#8230;' : '&#8594;'
}

// ── 우측 패널 ──
function openRightPanel(title, content, fullscreen = false) {
    panelTitle.textContent = title
    panelBody.innerHTML = content
    rightPanel.classList.add('open')
    const wrapper = document.querySelector('.page-wrapper')
    if (fullscreen) {
        wrapper.classList.add('chat-fullscreen')
    } else {
        wrapper.classList.remove('chat-fullscreen')
    }
}

function closeRightPanel() {
    rightPanel.classList.remove('open')
    document.querySelector('.page-wrapper').classList.remove('chat-fullscreen')
}

// ── Top 5 폴더 로드 ──
async function loadTopFolders() {
    try {
        const data = await fetch('/api/categories').then(r => r.json())
        const folderGrid = document.getElementById('folder-grid')

        let allCats = []
        Object.entries(data).forEach(([cat, subs]) => {
            subs.forEach(sub => allCats.push({ category: cat, name: sub.name, count: sub.count }))
        })
        allCats.sort((a, b) => b.count - a.count)
        const top5 = allCats.slice(0, 5)

        if (!top5.length) {
            folderGrid.innerHTML = '<div class="folder-placeholder">저장된 콘텐츠가 없어요</div>'
            return
        }

        folderGrid.innerHTML = top5.map(cat => `
            <div class="folder-card" onclick="openCategoryPanel('${esc(cat.category)}','${esc(cat.name)}')">
                <div class="folder-icon-wrap">
                    <div class="folder-tab"></div>
                    <div class="folder-body">
                        <div class="folder-papers">
                            <div class="folder-paper-line"></div>
                            <div class="folder-paper-line"></div>
                            <div class="folder-paper-line short"></div>
                        </div>
                    </div>
                </div>
                <div class="folder-meta">
                    <span class="folder-name">${cat.name || cat.category}</span>
                    <span class="folder-count">${cat.count}개</span>
                </div>
            </div>
        `).join('')
    } catch (e) {
        console.error('폴더 로드 실패:', e)
    }
}

// ── 카테고리 패널 열기 ──
async function openCategoryPanel(category, subcategory) {
    openRightPanel(`${category} / ${subcategory}`, '<div class="chat-loading">···</div>')
    try {
        const params = new URLSearchParams({ category, subcategory })
        const data = await fetch(`/api/items?${params}`).then(r => r.json())
        if (!data.items.length) {
            panelBody.innerHTML = '<p class="no-result">저장된 자료가 없어요.</p>'
            return
        }
        panelBody.innerHTML = data.items.map(item => {
            const tags = Array.isArray(item.tags) ? item.tags : []
            const thumbHTML = item.thumbnail
                ? `<img src="${item.thumbnail}" style="width:100%;height:130px;object-fit:cover;border-radius:8px;margin-bottom:10px;display:block" onerror="this.style.display='none'" alt="" />`
                : ''
            return `
                <div class="panel-item-card">
                    ${thumbHTML}
                    <p class="panel-item-title">${item.title}</p>
                    ${item.content_type !== 'music' && item.summary ? `<p class="panel-item-summary">${item.summary}</p>` : ''}
                    ${tags.length ? `<div class="card-tags" style="margin-bottom:8px">${tags.map(t => `<span class="tag">#${t}</span>`).join('')}</div>` : ''}
                    <a href="${item.url}" target="_blank" class="panel-item-link">링크 열기 &rarr;</a>
                </div>
            `
        }).join('')
    } catch (e) {
        panelBody.innerHTML = `<p class="error-msg">${e.message}</p>`
    }
}

// ── 컬렉션(폴더) 사이드바 로드 ──
async function loadCollections() {
    try {
        const data = await fetch(`/collections/${DEFAULT_USER_ID}`).then(r => r.json())
        const sidebar = document.getElementById('left-sidebar')
        const list    = document.getElementById('group-list')

        if (!data.collections || !data.collections.length) {
            sidebar.classList.remove('open')
            return
        }
        sidebar.classList.add('open')
        list.innerHTML = data.collections.map(c => `
            <div class="group-sidebar-item" onclick="openCollectionPanel('${esc(c.id)}','${esc(c.name)}')">
                <span class="group-sidebar-name">${c.emoji ? c.emoji + ' ' : ''}${c.name}</span>
            </div>
        `).join('')
    } catch (e) {
        console.error('컬렉션 로드 실패:', e)
    }
}

// ── 컬렉션 상세 패널 열기 ──
async function openCollectionPanel(collectionId, name) {
    openRightPanel(name, '<div class="chat-loading">···</div>')
    try {
        const data = await fetch(`/api/collections/${collectionId}/items?user_id=${DEFAULT_USER_ID}`).then(r => r.json())
        if (!data.items.length) {
            panelBody.innerHTML = '<p class="no-result">이 폴더에 자료가 없어요.</p>'
            return
        }
        panelBody.innerHTML = data.items.map(item => {
            const tags = Array.isArray(item.tags) ? item.tags : []
            const thumbHTML = item.thumbnail
                ? `<img src="${item.thumbnail}" style="width:100%;height:130px;object-fit:cover;border-radius:8px;margin-bottom:10px;display:block" onerror="this.style.display='none'" alt="" />`
                : ''
            return `
                <div class="panel-item-card">
                    ${thumbHTML}
                    <p class="panel-item-title">${item.title}</p>
                    ${item.summary ? `<p class="panel-item-summary">${item.summary}</p>` : ''}
                    ${tags.length ? `<div class="card-tags" style="margin-bottom:8px">${tags.map(t => `<span class="tag">#${t}</span>`).join('')}</div>` : ''}
                    <a href="${item.url}" target="_blank" class="panel-item-link">링크 열기 &rarr;</a>
                </div>
            `
        }).join('')
    } catch (e) {
        panelBody.innerHTML = `<p class="error-msg">${e.message}</p>`
    }
}

// ── AI 채팅 패널 열기 (전체화면) ──
function openChatPanel(initialText = '') {
    chatHistory = []
    shownIds = new Set()
    openRightPanel('AI 어시스턴트', `
        <div class="chat-container">
            <div class="chat-messages" id="chat-messages">
                <div class="chat-msg ai">안녕하세요! URL을 붙여넣으면 저장하고, 그 외 메시지는 AI와 대화할 수 있어요.</div>
            </div>
            <div class="chat-input-wrap">
                <input type="text" id="chat-input" class="chat-input" placeholder="URL 붙여넣기 또는 메시지 입력 (마감: 2026-06-01 형식으로 마감 추가 가능)" />
                <button id="chat-send" class="chat-send-btn">&#8594;</button>
            </div>
        </div>
    `, true)

    const chatInput = document.getElementById('chat-input')
    const chatSend  = document.getElementById('chat-send')
    chatSend.addEventListener('click', sendChat)
    chatInput.addEventListener('keydown', e => { if (e.key === 'Enter') sendChat() })
    chatInput.focus()

    if (initialText) {
        chatInput.value = initialText
        setTimeout(sendChat, 60)
    }
}

// ── 채팅 메시지 전송 (URL → 저장 / 텍스트 → AI 대화) ──
async function sendChat() {
    const chatInput    = document.getElementById('chat-input')
    const chatSend     = document.getElementById('chat-send')
    const chatMessages = document.getElementById('chat-messages')
    if (!chatInput) return

    const text = chatInput.value.trim()
    if (!text) return

    appendMsg(chatMessages, 'user', text)
    chatInput.value = ''
    chatSend.disabled = true

    const loadingEl = document.createElement('div')
    loadingEl.className = 'chat-loading'
    loadingEl.textContent = '···'
    chatMessages.appendChild(loadingEl)
    chatMessages.scrollTop = chatMessages.scrollHeight

    try {
        if (isURL(text.split(' ')[0])) {
            // URL → 저장
            const { url, deadline } = parseInput(text)
            const instruction = deadline ? `마감기한: ${deadline}` : ''
            const res = await fetch('/ingest', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, user_id: DEFAULT_USER_ID, instruction })
            })
            const data = await res.json()
            loadingEl.remove()
            if (!res.ok || data.error) throw new Error(data.error || '저장 실패')

            const aiEl = document.createElement('div')
            aiEl.className = 'chat-msg ai'

            if (data.duplicate) {
                aiEl.innerHTML = buildSavedItemContent(data.content, true)
            } else {
                aiEl.innerHTML = buildSavedItemContent(data)
                if (data.reminder_message) {
                    const reminderEl = document.createElement('div')
                    reminderEl.className = 'chat-msg ai'
                    reminderEl.textContent = data.reminder_message
                    chatMessages.appendChild(aiEl)
                    chatMessages.appendChild(reminderEl)
                    chatMessages.scrollTop = chatMessages.scrollHeight
                    loadTopFolders()
                    loadCollections()
                    return
                }
            }
            chatMessages.appendChild(aiEl)
            loadTopFolders()
            loadCollections()
        } else {
            // 텍스트 → AI 대화
            chatHistory.push({ role: 'user', content: text })
            const res = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: text,
                    user_id: DEFAULT_USER_ID,
                    history: chatHistory.slice(-10),
                    shown_ids: [...shownIds],
                })
            })
            const data = await res.json()
            loadingEl.remove()

            // 보여준 결과 ID 누적
            if (data.results) {
                data.results.forEach(r => r.id && shownIds.add(r.id))
            }
            chatHistory.push({ role: 'assistant', content: data.answer || '' })

            const aiEl = document.createElement('div')
            aiEl.className = 'chat-msg ai'
            aiEl.innerHTML = buildAIContent(data)
            chatMessages.appendChild(aiEl)
            loadCollections()
        }
    } catch (e) {
        loadingEl.remove()
        appendMsg(chatMessages, 'ai', `오류: ${e.message}`)
    } finally {
        chatSend.disabled = false
        chatMessages.scrollTop = chatMessages.scrollHeight
    }
}

// URL 저장 결과를 채팅 버블로 표시
function buildSavedItemContent(item, isDuplicate = false) {
    const tags = Array.isArray(item.tags) ? item.tags : (item.tags ? JSON.parse(item.tags) : [])
    const thumbHTML = item.thumbnail
        ? `<img src="${item.thumbnail}" style="width:100%;height:140px;object-fit:cover;border-radius:8px;margin-bottom:10px;display:block" onerror="this.style.display='none'" alt="" />`
        : ''
    const statusText = isDuplicate ? '이미 저장된 콘텐츠예요' : '✓ 저장 완료'
    const statusColor = isDuplicate ? '#9A7055' : '#5A9A60'
    const summary = item.one_line_summary || item.description || ''
    const subcat = item.sub_category || item.subcategory || ''
    return `
        <div style="font-size:11px;font-weight:700;color:${statusColor};margin-bottom:8px;letter-spacing:0.3px">${statusText}</div>
        ${thumbHTML}
        <div style="font-size:14px;font-weight:600;color:#2C1A0E;margin-bottom:4px;line-height:1.4">${item.title}</div>
        <div style="font-size:12px;color:#9A7055;margin-bottom:8px">${item.category || ''}${subcat ? ' / ' + subcat : ''}</div>
        ${summary ? `<div style="font-size:13px;color:#6B4E3A;line-height:1.55;margin-bottom:8px">${summary}</div>` : ''}
        ${tags.length ? `<div class="card-tags" style="margin-bottom:8px">${tags.map(t => `<span class="tag">#${t}</span>`).join('')}</div>` : ''}
        <a href="${item.url}" target="_blank" class="panel-item-link" style="margin-top:4px;display:inline-block">링크 열기 &rarr;</a>
    `
}

function appendMsg(container, role, text) {
    const el = document.createElement('div')
    el.className = `chat-msg ${role}`
    el.textContent = text
    container.appendChild(el)
    container.scrollTop = container.scrollHeight
}

// 검색 결과 카드 HTML
function buildResultCards(items, maxCount = 5) {
    const preview = items.slice(0, maxCount)
    const more    = items.length - maxCount
    const cardsHTML = preview.map(item => {
        const summary = item.one_line_summary || item.summary || ''
        return `
            <a href="${item.url}" target="_blank" class="msg-result-card">
                <div class="msg-card-thumb-placeholder">📄</div>
                <div class="msg-card-body">
                    <div class="msg-card-title">${item.title}</div>
                    ${summary ? `<div class="msg-card-summary">${summary}</div>` : ''}
                    <span class="msg-card-link">링크 열기 →</span>
                </div>
            </a>
        `
    }).join('')
    return `<div class="msg-result-cards">${cardsHTML}${more > 0 ? `<span class="msg-more">외 ${more}개</span>` : ''}</div>`
}

// AI 응답 HTML 빌드
function buildAIContent(data) {
    let html = data.answer || ''

    if (data.results && data.results.length) {
        html += buildResultCards(data.results)
    }

    if (data.follow_up_questions && data.follow_up_questions.length) {
        html += `<div class="follow-up-questions">${data.follow_up_questions.map(q =>
            `<button class="follow-up-btn" onclick="followUp(this)">${q}</button>`
        ).join('')}</div>`
    }


    return html
}

// 후속 질문 버튼 클릭 시 채팅 입력에 삽입
window.followUp = function(btn) {
    const chatInput = document.getElementById('chat-input')
    if (chatInput) {
        chatInput.value = btn.textContent
        chatInput.focus()
    }
}

// ── 메인 submit 핸들러 → 채팅 패널로 통합 ──
function handleSubmit() {
    const text = promptInput.value.trim()
    if (!text) return
    promptInput.value = ''
    openChatPanel(text)
}

// ── 아카이브 모달 ──
async function showArchiveHome() {
    const data = await fetch('/api/categories').then(r => r.json())
    const keys = Object.keys(data)
    if (!keys.length) {
        openModal('아카이브', '<p class="no-result">저장된 자료가 없어요.</p>')
        return
    }
    const html = keys.map(cat => `
        <div class="archive-cat">
            <h3 class="cat-name">${cat}</h3>
            ${data[cat].map(s => `
                <div class="sub-item" onclick="showArchiveItems('${esc(cat)}','${esc(s.name)}')">
                    <span>${s.name ?? '미분류'}</span>
                    <span class="sub-count">${s.count}개 &rsaquo;</span>
                </div>
            `).join('')}
        </div>
    `).join('')
    openModal('아카이브', html)
}

async function showArchiveItems(category, subcategory) {
    const params = new URLSearchParams({ category, subcategory })
    const data   = await fetch(`/api/items?${params}`).then(r => r.json())
    const cards  = data.items.length
        ? data.items.map(item => {
            const tags = Array.isArray(item.tags) ? item.tags : []
            const date = item.saved_at ? item.saved_at.slice(0, 10) : ''
            return `
                <div class="archive-item-card">
                    ${item.content_type !== 'music' && item.summary ? `<p class="archive-item-summary">${item.summary}</p>` : ''}
                    <p class="archive-item-title">${item.title}</p>
                    ${tags.length ? `<div class="archive-item-tags">${tags.map(t => `<span class="tag">#${t}</span>`).join('')}</div>` : ''}
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
                        <span class="archive-item-meta">${date}</span>
                        <a href="${item.url}" target="_blank" class="archive-item-link">링크 열기 &rarr;</a>
                    </div>
                </div>
            `
          }).join('')
        : '<p class="no-result">저장된 자료가 없어요.</p>'
    openModal(`${category} / ${subcategory}`, `<button class="back-btn" onclick="showArchiveHome()">&#8592; 전체 카테고리</button>${cards}`)
}

function openModal(title, content) {
    modalBody.innerHTML = `<h2 class="modal-title">${title}</h2>${content}`
    modal.classList.add('open')
}

function closeModal() {
    modal.classList.remove('open')
}

function esc(str) {
    return (str ?? '').toString().replace(/\\/g, '\\\\').replace(/'/g, "\\'")
}

// ── 이벤트 바인딩 ──
document.getElementById('btn-archives').addEventListener('click', showArchiveHome)
document.getElementById('panel-close').addEventListener('click', closeRightPanel)
document.getElementById('modal-close').addEventListener('click', closeModal)
modal.addEventListener('click', e => { if (e.target === modal) closeModal() })
submitBtn.addEventListener('click', handleSubmit)
promptInput.addEventListener('keydown', e => { if (e.key === 'Enter') handleSubmit() })

// ── 리마인더 캘린더 ──
let calYear  = new Date().getFullYear()
let calMonth = new Date().getMonth()
let calDeadlines = []

function renderCalendar(year, month) {
    const today    = new Date().toISOString().slice(0, 10)
    const dayNames = ['일', '월', '화', '수', '목', '금', '토']
    const monthNames = ['1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월']

    // 날짜 → 마감 항목 맵
    const dateMap = {}
    calDeadlines.forEach(d => {
        if (d.deadline_date) {
            if (!dateMap[d.deadline_date]) dateMap[d.deadline_date] = []
            dateMap[d.deadline_date].push(d)
        }
    })

    const firstDay    = new Date(year, month, 1).getDay()
    const daysInMonth = new Date(year, month + 1, 0).getDate()

    // 요일 헤더
    let gridHTML = dayNames.map(d => `<div class="cal-day-label">${d}</div>`).join('')

    // 빈 칸
    for (let i = 0; i < firstDay; i++) gridHTML += '<div class="cal-cell empty"></div>'

    // 날짜 칸
    for (let day = 1; day <= daysInMonth; day++) {
        const ds  = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
        const isToday   = ds === today
        const items     = dateMap[ds]
        const isPast    = items && ds < today

        let cls = 'cal-cell'
        if (isToday)   cls += ' today'
        if (items)     cls += ' has-deadline'
        if (isPast)    cls += ' past-deadline'

        gridHTML += `
            <div class="${cls}" ${items ? `onclick="showDayDetail('${ds}')" id="cal-${ds}"` : ''}>
                <span>${day}</span>
                ${items ? '<span class="cal-dot"></span>' : ''}
            </div>`
    }

    // 다가오는 마감 목록
    const upcoming = calDeadlines
        .filter(d => d.deadline_date && d.deadline_date >= today)
        .sort((a, b) => a.deadline_date.localeCompare(b.deadline_date))

    const listHTML = upcoming.length
        ? upcoming.map(d => `
            <div class="reminder-item">
                <span class="reminder-deadline">마감: ${d.deadline_date}</span>
                <p class="reminder-title">${d.title}</p>
                ${d.deadline_note ? `<span class="reminder-cat">${d.deadline_note}</span>` : ''}
                <a href="${d.url}" target="_blank" class="card-link">링크 열기 &rarr;</a>
            </div>`).join('')
        : '<p class="no-result">다가오는 마감이 없어요.</p>'

    return `
        <div class="cal-header">
            <button class="cal-nav-btn" onclick="moveCalendar(-1)">‹</button>
            <span>${year}년 ${monthNames[month]}</span>
            <button class="cal-nav-btn" onclick="moveCalendar(1)">›</button>
        </div>
        <div class="cal-grid">${gridHTML}</div>
        <div id="cal-day-detail"></div>
        <p class="cal-section-title">다가오는 마감</p>
        ${listHTML}
    `
}

window.moveCalendar = function(dir) {
    calMonth += dir
    if (calMonth > 11) { calMonth = 0; calYear++ }
    if (calMonth < 0)  { calMonth = 11; calYear-- }
    modalBody.innerHTML = '<h2 class="modal-title">리마인더</h2>' + renderCalendar(calYear, calMonth)
}

window.showDayDetail = function(ds) {
    // 선택 표시 초기화
    document.querySelectorAll('.cal-cell.selected').forEach(el => el.classList.remove('selected'))
    const cell = document.getElementById(`cal-${ds}`)
    if (cell) cell.classList.add('selected')

    const items = calDeadlines.filter(d => d.deadline_date === ds)
    const detail = document.getElementById('cal-day-detail')
    if (!detail) return

    detail.innerHTML = `
        <div class="cal-day-detail">
            <p class="cal-day-detail-title">📅 ${ds}</p>
            ${items.map(d => `
                <div style="margin-bottom:10px">
                    <p style="font-size:14px;font-weight:600;color:#2C1A0E;margin-bottom:4px">${d.title}</p>
                    ${d.deadline_note ? `<p style="font-size:12px;color:#9A7055;margin-bottom:4px">${d.deadline_note}</p>` : ''}
                    <a href="${d.url}" target="_blank" class="card-link">링크 열기 &rarr;</a>
                </div>
            `).join('')}
        </div>
    `
}

document.getElementById('btn-reminders').addEventListener('click', async () => {
    const data = await fetch(`/deadlines/${DEFAULT_USER_ID}`).then(r => r.json())
    calDeadlines = data.deadlines || []
    calYear  = new Date().getFullYear()
    calMonth = new Date().getMonth()

    if (!calDeadlines.length) {
        openModal('리마인더', '<p class="no-result">마감 자료가 없어요.</p>')
        return
    }
    openModal('리마인더', renderCalendar(calYear, calMonth))
})

document.getElementById('btn-report').addEventListener('click', async () => {
    const data = await fetch('/api/monthly-report').then(r => r.json())
    const statsHtml = data.stats.map(s => `
        <div class="stat-row">
            <span>${s.category}</span>
            <span class="stat-count">${s.count}개</span>
        </div>
    `).join('')
    openModal('월간 취향 레포트', `
        <div class="report-text">${data.report}</div>
        ${statsHtml ? `<div class="stats-list">${statsHtml}</div>` : ''}
    `)
})

document.getElementById('btn-weekly-report').addEventListener('click', () => {
    const overlay = document.createElement('div')
    overlay.id = 'weekly-report-overlay'
    overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:#fdf8f5;'
    overlay.innerHTML = `
        <button onclick="document.getElementById('weekly-report-overlay').remove()"
            style="position:fixed;top:16px;right:20px;z-index:10000;background:#6b3a2a;color:#fdf3ec;border:none;border-radius:20px;padding:8px 20px;font-size:14px;font-weight:700;cursor:pointer;">
            ✕ 닫기
        </button>
        <iframe src="/weekly-report" style="width:100%;height:100%;border:none;display:block;"></iframe>
    `
    document.body.appendChild(overlay)
})

// ── 초기 로드 ──
loadTopFolders()
loadCollections()
