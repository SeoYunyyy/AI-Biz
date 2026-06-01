// ── Keepit 메인 인터랙션 ──

// 로그인한 사용자 id (index.html에서 주입). 없으면 기본 계정으로 폴백
const DEFAULT_USER_ID = window.__USER_ID__ || '00000000-0000-0000-0000-000000000001'

// 채팅 세션 상태 (패널 열릴 때 초기화)
let chatHistory = []
let shownIds = new Set()

// 리마인더 캘린더 상태
let calYear  = new Date().getFullYear()
let calMonth = new Date().getMonth() // 0-indexed
let calDeadlines = []
let calSelectedDate = null

// 아카이브 상태
let archiveData     = {}
let archiveExpanded = {}

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
        const data = await fetch(`/api/categories?user_id=${DEFAULT_USER_ID}`).then(r => r.json())
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
        const params = new URLSearchParams({ category, subcategory, user_id: DEFAULT_USER_ID })
        const data = await fetch(`/api/items?${params}`).then(r => r.json())
        if (!data.items.length) {
            panelBody.innerHTML = '<p class="no-result">저장된 자료가 없어요.</p>'
            return
        }
        panelBody.innerHTML = data.items.map(item => {
            const tags = Array.isArray(item.tags) ? item.tags : []
            const thumb = item.thumbnail || item.thumbnail_url || ''
            const thumbHTML = thumb
                ? `<img src="${thumb}" style="width:100%;height:130px;object-fit:cover;border-radius:8px;margin-bottom:10px;display:block" onerror="this.style.display='none'" alt="" />`
                : ''
            return `
                <div class="panel-item-card">
                    ${thumbHTML}
                    <p class="panel-item-title">${item.title}</p>
                    ${item.content_type !== 'music' && item.summary ? buildCollapsibleSummary(item.summary, 'panel-item-summary') : ''}
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

// ── 컬렉션 상세 패널 열기 (이름 수정 / 폴더 삭제 / 폴더에서 빼기 포함) ──
async function openCollectionPanel(collectionId, name) {
    openRightPanel(name, '<div class="chat-loading">···</div>')
    try {
        const data = await fetch(`/api/collections/${collectionId}/items?user_id=${DEFAULT_USER_ID}`).then(r => r.json())

        // 폴더 관리 헤더 (이름 변경 + 폴더 삭제)
        const manageHTML = `
            <div class="collection-manage">
                <div class="collection-rename-row">
                    <input id="collection-rename-input" class="collection-rename-input" value="${(name ?? '').replace(/"/g, '&quot;')}" />
                    <button class="manage-btn" onclick="renameCollection('${esc(collectionId)}')">이름 저장</button>
                </div>
                <button class="manage-btn danger" onclick="deleteCollection('${esc(collectionId)}','${esc(name)}')">폴더 삭제</button>
            </div>
        `

        if (!data.items.length) {
            panelBody.innerHTML = manageHTML + '<p class="no-result">이 폴더에 자료가 없어요.</p>'
            return
        }
        panelBody.innerHTML = manageHTML + data.items.map(item => {
            const tags = Array.isArray(item.tags) ? item.tags : []
            const thumb = item.thumbnail || item.thumbnail_url || ''
            const thumbHTML = thumb
                ? `<img src="${thumb}" style="width:100%;height:130px;object-fit:cover;border-radius:8px;margin-bottom:10px;display:block" onerror="this.style.display='none'" alt="" />`
                : ''
            return `
                <div class="panel-item-card">
                    ${thumbHTML}
                    <p class="panel-item-title">${item.title}</p>
                    ${item.summary ? buildCollapsibleSummary(item.summary, 'panel-item-summary') : ''}
                    ${tags.length ? `<div class="card-tags" style="margin-bottom:8px">${tags.map(t => `<span class="tag">#${t}</span>`).join('')}</div>` : ''}
                    <div class="panel-item-actions">
                        <a href="${item.url}" target="_blank" class="panel-item-link">링크 열기 &rarr;</a>
                        <button class="item-remove-btn" onclick="removeFromCollection('${esc(collectionId)}','${esc(item.id)}','${esc(name)}')">폴더에서 빼기</button>
                    </div>
                </div>
            `
        }).join('')
    } catch (e) {
        panelBody.innerHTML = `<p class="error-msg">${e.message}</p>`
    }
}

// ── 컬렉션 이름 변경 ──
window.renameCollection = async function (collectionId) {
    const input = document.getElementById('collection-rename-input')
    const name = (input?.value || '').trim()
    if (!name) return
    try {
        const res = await fetch(`/collections/${collectionId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: DEFAULT_USER_ID, name }),
        })
        if (!res.ok) throw new Error('이름 변경 실패')
        panelTitle.textContent = name
        loadCollections()
    } catch (e) {
        alert('이름 변경 실패: ' + e.message)
    }
}

// ── 컬렉션(폴더) 삭제 — 폴더만 삭제, 콘텐츠는 보관 ──
window.deleteCollection = async function (collectionId, name) {
    if (!confirm(`'${name}' 폴더를 삭제할까요?\n폴더만 삭제되고 안의 콘텐츠는 보관됩니다.`)) return
    try {
        const res = await fetch(`/collections/${collectionId}?user_id=${DEFAULT_USER_ID}`, { method: 'DELETE' })
        if (!res.ok) throw new Error('삭제 실패')
        closeRightPanel()
        loadTopFolders()
        loadCollections()
    } catch (e) {
        alert('폴더 삭제 실패: ' + e.message)
    }
}

// ── 폴더에서 콘텐츠 빼기 (콘텐츠 자체는 보존) ──
window.removeFromCollection = async function (collectionId, contentId, name) {
    try {
        const res = await fetch(`/collections/${collectionId}/items/${contentId}?user_id=${DEFAULT_USER_ID}`, { method: 'DELETE' })
        if (!res.ok) throw new Error('빼기 실패')
        openCollectionPanel(collectionId, name)
        loadCollections()
    } catch (e) {
        alert('폴더에서 빼기 실패: ' + e.message)
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
        const thumb = item.thumbnail || item.thumbnail_url || ''
        const thumbHTML = thumb
            ? `<img src="${thumb}" class="msg-card-thumb" onerror="this.style.display='none'" alt="" />`
            : `<div class="msg-card-thumb-placeholder">📄</div>`
        return `
            <a href="${item.url}" target="_blank" class="msg-result-card">
                ${thumbHTML}
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
            `<p class="follow-up-text">${q}</p>`
        ).join('')}</div>`
    }

    // 폴더 생성 완료 시 → 그룹 수정(이름 변경 / 콘텐츠 빼기) 진입 버튼
    if (data.action === 'folder_created' && data.collection_id) {
        html += `<div class="folder-edit-row">
            <button class="folder-edit-btn" onclick="openCollectionPanel('${esc(data.collection_id)}','${esc(data.collection_name)}')">그룹 수정하기</button>
        </div>`
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
    archiveData     = await fetch(`/api/categories?user_id=${DEFAULT_USER_ID}`).then(r => r.json())
    archiveExpanded = {}
    if (!Object.keys(archiveData).length) {
        openModal('아카이브', '<p class="no-result">저장된 자료가 없어요.</p>')
        return
    }
    openModal('아카이브', `
        <div class="archive-search-wrap">
            <input type="text" id="archive-search" class="archive-search"
                placeholder="🔍 카테고리나 항목 검색..."
                oninput="renderArchiveCats(this.value)" />
        </div>
        <div id="archive-cat-list"></div>
    `)
    renderArchiveCats('')
}

function _subItemHTML(cat, s) {
    return `
        <div class="sub-item" onclick="showArchiveItems('${esc(cat)}','${esc(s.name)}')">
            <span>${s.name ?? '미분류'}</span>
            <span class="sub-right">
                <span class="sub-count">${s.count}개 &rsaquo;</span>
                <button class="sub-del-btn" title="중분류 삭제"
                    onclick="event.stopPropagation();deleteSubcategory('${esc(cat)}','${esc(s.name)}')">🗑</button>
            </span>
        </div>`
}

function renderArchiveCats(query) {
    const el = document.getElementById('archive-cat-list')
    if (!el) return
    const q = query.toLowerCase().trim()
    let html = ''
    let hasAny = false

    Object.entries(archiveData).forEach(([cat, items]) => {
        const catMatch = cat.toLowerCase().includes(q)
        const filtered = q
            ? (catMatch ? items : items.filter(s => s.name?.toLowerCase().includes(q)))
            : items
        if (!filtered.length) return
        hasAny = true

        const sorted   = [...filtered].sort((a, b) => b.count - a.count)
        const visible  = q ? sorted : sorted.filter(s => s.count >= 2)
        const hidden   = q ? []     : sorted.filter(s => s.count < 2)
        const expanded = archiveExpanded[cat]

        html += `<div class="archive-cat"><h3 class="cat-name">${cat}</h3>`
        html += visible.map(s => _subItemHTML(cat, s)).join('')
        if (hidden.length) {
            if (expanded) {
                html += hidden.map(s => _subItemHTML(cat, s)).join('')
                html += `<button class="archive-more-btn" onclick="window.toggleArchiveCat('${esc(cat)}',false)">접기 ▴</button>`
            } else {
                html += `<button class="archive-more-btn" onclick="window.toggleArchiveCat('${esc(cat)}',true)">더보기 ${hidden.length}개 ▾</button>`
            }
        }
        html += `</div>`
    })

    el.innerHTML = hasAny ? html : '<p class="no-result">검색 결과가 없어요.</p>'
}

window.toggleArchiveCat = function(cat, expand) {
    archiveExpanded[cat] = expand
    renderArchiveCats(document.getElementById('archive-search')?.value || '')
}

async function showArchiveItems(category, subcategory) {
    const params = new URLSearchParams({ category, subcategory, user_id: DEFAULT_USER_ID })
    const data   = await fetch(`/api/items?${params}`).then(r => r.json())
    const cards  = data.items.length
        ? data.items.map(item => {
            const tags = Array.isArray(item.tags) ? item.tags : []
            const date = item.saved_at ? item.saved_at.slice(0, 10) : ''
            const thumbHTML = item.thumbnail
                ? `<img src="${item.thumbnail}" class="archive-item-thumb" onerror="this.style.display='none'" alt="" />`
                : ''
            return `
                <div class="archive-item-card">
                    ${thumbHTML}
                    ${item.content_type !== 'music' && item.summary ? buildCollapsibleSummary(item.summary, 'archive-item-summary') : ''}
                    <p class="archive-item-title">${item.title}</p>
                    ${tags.length ? `<div class="archive-item-tags">${tags.map(t => `<span class="tag">#${t}</span>`).join('')}</div>` : ''}
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
                        <span class="archive-item-meta">${date}</span>
                        <div class="archive-item-btns">
                            <a href="${item.url}" target="_blank" class="archive-item-link">링크 열기 &rarr;</a>
                            <button class="archive-del-btn"
                                onclick="deleteArchiveContent('${esc(item.id)}','${esc(category)}','${esc(subcategory)}')">삭제</button>
                        </div>
                    </div>
                </div>
            `
          }).join('')
        : '<p class="no-result">저장된 자료가 없어요.</p>'
    openModal(`${category} / ${subcategory}`, `<button class="back-btn" onclick="showArchiveHome()">&#8592; 전체 카테고리</button>${cards}`)
}

// ── 중분류 삭제 (안의 콘텐츠 전체 영구 삭제) ──
window.deleteSubcategory = async function (category, subcategory) {
    if (!confirm(`'${subcategory}' 중분류와 그 안의 모든 콘텐츠를 영구 삭제할까요?\n되돌릴 수 없습니다.`)) return
    try {
        const params = new URLSearchParams({ category, subcategory, user_id: DEFAULT_USER_ID })
        const res = await fetch(`/api/subcategory?${params}`, { method: 'DELETE' })
        if (!res.ok) throw new Error('삭제 실패')
        showArchiveHome()
        loadTopFolders()
    } catch (e) {
        alert('중분류 삭제 실패: ' + e.message)
    }
}

// ── 아카이브 콘텐츠 1건 영구 삭제 ──
window.deleteArchiveContent = async function (contentId, category, subcategory) {
    if (!confirm('이 콘텐츠를 영구 삭제할까요?')) return
    try {
        const res = await fetch(`/contents/${contentId}?user_id=${DEFAULT_USER_ID}`, { method: 'DELETE' })
        if (!res.ok) throw new Error('삭제 실패')
        showArchiveItems(category, subcategory)
        loadTopFolders()
    } catch (e) {
        alert('삭제 실패: ' + e.message)
    }
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

// 긴 요약 접기/펼치기 헬퍼
function buildCollapsibleSummary(summary, className, threshold = 80) {
    if (!summary) return ''
    if (summary.length <= threshold) return `<p class="${className}">${summary}</p>`
    const id = 'sum-' + Math.random().toString(36).slice(2, 8)
    return `<p class="${className} summary-collapsed" id="${id}">${summary}</p><button class="summary-toggle" onclick="toggleSummary('${id}',this)">더 보기</button>`
}

window.toggleSummary = function(id, btn) {
    const el = document.getElementById(id)
    if (!el) return
    el.classList.toggle('summary-collapsed')
    btn.textContent = el.classList.contains('summary-collapsed') ? '더 보기' : '접기'
}

// ── 이벤트 바인딩 ──
document.getElementById('btn-archives').addEventListener('click', showArchiveHome)
document.getElementById('panel-close').addEventListener('click', closeRightPanel)
document.getElementById('modal-close').addEventListener('click', closeModal)
modal.addEventListener('click', e => { if (e.target === modal) closeModal() })
submitBtn.addEventListener('click', handleSubmit)
promptInput.addEventListener('keydown', e => { if (e.key === 'Enter') handleSubmit() })

document.getElementById('btn-reminders').addEventListener('click', async () => {
    const data = await fetch(`/deadlines/${DEFAULT_USER_ID}`).then(r => r.json())
    if (!data.deadlines || !data.deadlines.length) {
        openModal('리마인더', '<p class="no-result">마감 자료가 없어요.</p>')
        return
    }
    const now = new Date()
    calYear      = now.getFullYear()
    calMonth     = now.getMonth()
    calDeadlines = data.deadlines
    renderReminderCalendar()
})

function renderReminderCalendar() {
    const MONTHS = ['1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월']
    const todayStr = new Date().toISOString().slice(0, 10)
    const monthPad = String(calMonth + 1).padStart(2, '0')

    // 날짜별 deadline 맵핑
    const dateMap = {}
    calDeadlines.forEach(r => {
        if (r.deadline_date) {
            if (!dateMap[r.deadline_date]) dateMap[r.deadline_date] = []
            dateMap[r.deadline_date].push(r)
        }
    })

    // 달력 셀 생성
    const firstDow = new Date(calYear, calMonth, 1).getDay()
    const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate()
    const weekdays = ['일','월','화','수','목','금','토']

    let cellsHTML = weekdays.map((d, i) =>
        `<div class="cal-weekday ${i===0?'sun':i===6?'sat':''}">${d}</div>`
    ).join('')

    // 이전 달 빈 칸
    const prevDays = new Date(calYear, calMonth, 0).getDate()
    for (let i = firstDow - 1; i >= 0; i--) {
        cellsHTML += `<div class="cal-cell other-month"><div class="cal-dots"></div><div class="cal-date-num">${prevDays - i}</div></div>`
    }

    // 이번 달 날짜
    for (let d = 1; d <= daysInMonth; d++) {
        const dateStr = `${calYear}-${monthPad}-${String(d).padStart(2,'0')}`
        const dow = (firstDow + d - 1) % 7
        const items = dateMap[dateStr] || []
        const dots  = Array(Math.min(items.length, 4)).fill('<div class="cal-dot"></div>').join('')
        const cls   = [
            dateStr === todayStr ? 'today' : '',
            dow === 0 ? 'sunday' : '',
            dow === 6 ? 'saturday' : ''
        ].join(' ')
        const isSel = dateStr === calSelectedDate ? 'selected' : ''
        cellsHTML += `
            <div class="cal-cell ${cls} ${isSel}" onclick="window.calSelectDate('${dateStr}')">
                <div class="cal-dots">${dots}</div>
                <div class="cal-date-num">${d}</div>
            </div>`
    }

    // 다음 달 빈 칸
    const total = firstDow + daysInMonth
    const trailing = total % 7 === 0 ? 0 : 7 - (total % 7)
    for (let i = 1; i <= trailing; i++) {
        cellsHTML += `<div class="cal-cell other-month"><div class="cal-dots"></div><div class="cal-date-num">${i}</div></div>`
    }

    // 이벤트 목록: 날짜 선택 시 해당 날만, 아니면 이번 달 전체
    const monthStart = `${calYear}-${monthPad}-01`
    const monthEnd   = `${calYear}-${monthPad}-${String(daysInMonth).padStart(2,'0')}`
    const listItems = calSelectedDate
        ? calDeadlines.filter(r => r.deadline_date === calSelectedDate)
        : calDeadlines
            .filter(r => r.deadline_date >= monthStart && r.deadline_date <= monthEnd)
            .sort((a, b) => a.deadline_date.localeCompare(b.deadline_date))

    const filterBarHTML = calSelectedDate ? `
        <div class="cal-filter-bar">
            <span>📌 ${calSelectedDate} 마감 콘텐츠</span>
            <button class="cal-filter-clear" onclick="window.calClearFilter()">전체 보기 ✕</button>
        </div>` : ''

    const noMsg = calSelectedDate
        ? '이 날 마감 콘텐츠가 없어요.'
        : '이 달에 마감 자료가 없어요.'

    let eventListHTML = filterBarHTML + (listItems.length
        ? listItems.map(r => {
            const exp = r.deadline_date < todayStr
            return `
                <div class="cal-event-item ${exp ? 'expired' : ''}">
                    <div class="cal-event-deadline">${exp ? '⏰ 만료 · ' : '📌 '}${r.deadline_date}</div>
                    <div class="cal-event-title">${r.title}</div>
                    ${r.deadline_note ? `<div class="cal-event-note">${r.deadline_note}</div>` : ''}
                    <a href="${r.url}" target="_blank" class="cal-event-link">링크 열기 →</a>
                </div>`
        }).join('')
        : `<div class="cal-no-events">${noMsg}</div>`)

    const html = `
        <div class="cal-container">
            <div class="cal-header">
                <span class="cal-month-title">${calYear}년 ${MONTHS[calMonth]}</span>
                <div class="cal-nav">
                    <button class="cal-nav-btn cal-today-btn" onclick="window.calNavigate(0)">오늘</button>
                    <button class="cal-nav-btn" onclick="window.calNavigate(-1)">‹</button>
                    <button class="cal-nav-btn" onclick="window.calNavigate(1)">›</button>
                </div>
            </div>
            <div class="cal-grid">${cellsHTML}</div>
            <div class="cal-event-list">${eventListHTML}</div>
        </div>`

    openModal('리마인더', html)
}

window.calNavigate = function(dir) {
    calSelectedDate = null
    if (dir === 0) {
        const now = new Date()
        calYear = now.getFullYear(); calMonth = now.getMonth()
    } else {
        calMonth += dir
        if (calMonth < 0)  { calMonth = 11; calYear-- }
        if (calMonth > 11) { calMonth = 0;  calYear++ }
    }
    renderReminderCalendar()
}

window.calSelectDate = function(dateStr) {
    calSelectedDate = calSelectedDate === dateStr ? null : dateStr
    renderReminderCalendar()
}

window.calClearFilter = function() {
    calSelectedDate = null
    renderReminderCalendar()
}

document.getElementById('btn-report').addEventListener('click', () => {
    const overlay = document.createElement('div')
    overlay.id = 'monthly-report-overlay'
    overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:#fdf8f5;'
    overlay.innerHTML = `
        <button onclick="document.getElementById('monthly-report-overlay').remove()"
            style="position:fixed;top:16px;right:20px;z-index:10000;background:#6b3a2a;color:#fdf3ec;border:none;border-radius:20px;padding:8px 20px;font-size:14px;font-weight:700;cursor:pointer;">
            ✕ 닫기
        </button>
        <iframe src="/monthly-report?user_id=${DEFAULT_USER_ID}" style="width:100%;height:100%;border:none;display:block;"></iframe>
    `
    document.body.appendChild(overlay)
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
        <iframe src="/weekly-report?user_id=${DEFAULT_USER_ID}" style="width:100%;height:100%;border:none;display:block;"></iframe>
    `
    document.body.appendChild(overlay)
})

// ── 초기 로드 ──
loadTopFolders()
loadCollections()
