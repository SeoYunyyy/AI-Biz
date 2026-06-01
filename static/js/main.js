// ── Keepit 메인 인터랙션 ──

// ── 인증 ──────────────────────────────────────────────────────────────────────
function getCurrentUserId()   { return localStorage.getItem('keepit_user_id') || '' }
function getCurrentUsername() { return localStorage.getItem('keepit_username') || '' }
function isLoggedIn()         { return !!getCurrentUserId() }

function initAuth() {
    // OAuth 콜백: URL에 ?user_id=&username= 붙어서 돌아옴
    const params = new URLSearchParams(window.location.search)
    const oauthUserId   = params.get('user_id')
    const oauthUsername = params.get('username')
    if (oauthUserId && oauthUsername) {
        localStorage.setItem('keepit_user_id', oauthUserId)
        localStorage.setItem('keepit_username', decodeURIComponent(oauthUsername))
        window.history.replaceState({}, '', '/')
    }

    const overlay = document.getElementById('login-overlay')
    if (isLoggedIn()) {
        overlay.classList.add('hidden')
        document.getElementById('nav-username').textContent = getCurrentUsername()
    } else {
        overlay.classList.remove('hidden')
    }
}

window.handleLogout = function() {
    localStorage.removeItem('keepit_user_id')
    localStorage.removeItem('keepit_username')
    location.reload()
}
// ── 인증 끝 ──────────────────────────────────────────────────────────────────

// 채팅 세션 상태
let chatHistory = []
let shownIds = new Set()
let currentContentId = null      // 마지막 저장 콘텐츠 ID (deadline_edit용)
let selectedCollectionId = null  // 폴더 선택 (메인 입력창)
let selectedCollectionName = null

// ── 아카이브 상태 ──
let archiveData     = {}
let archiveExpanded = {}

// ── 리마인더 캘린더 상태 ──
let calYear         = new Date().getFullYear()
let calMonth        = new Date().getMonth()
let calDeadlines    = []
let calSelectedDate = null

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

// ── 폴더 선택 (메인 프롬프트 박스) ──
async function initFolderPicker() {
    const btn      = document.getElementById('folder-picker-btn')
    const dropdown = document.getElementById('folder-dropdown')
    if (!btn || !dropdown) return

    btn.addEventListener('click', async (e) => {
        e.stopPropagation()
        if (dropdown.classList.contains('open')) {
            dropdown.classList.remove('open')
            return
        }
        await populateFolderDropdown(dropdown, (id, name) => {
            selectedCollectionId   = id
            selectedCollectionName = name
            btn.textContent = name ? `📁 ${name}` : '📁'
            btn.classList.toggle('active', !!id)
            dropdown.classList.remove('open')
        })
        dropdown.classList.add('open')
    })

    document.addEventListener('click', () => dropdown.classList.remove('open'))
}

async function populateFolderDropdown(dropdown, onSelect) {
    dropdown.innerHTML = '<div class="folder-option" style="color:#9A7055">불러오는 중···</div>'
    try {
        const data = await fetch(`/collections/${getCurrentUserId()}`).then(r => r.json())
        const cols = data.collections || []
        dropdown.innerHTML = `
            <div class="folder-option selected" onclick="(${onSelect.toString()})(null, null)">선택 안 함</div>
            ${cols.map(c => `
                <div class="folder-option" onclick="(${onSelect.toString()})('${esc(c.id)}', '${esc(c.name)}')">
                    ${c.emoji ? c.emoji + ' ' : ''}${c.name}
                </div>
            `).join('')}
        `
    } catch (e) {
        dropdown.innerHTML = '<div class="folder-option" style="color:#C0392B">불러오기 실패</div>'
    }
}

// ── Top 5 폴더 로드 ──
async function loadTopFolders() {
    try {
        const data = await fetch(`/api/categories?user_id=${getCurrentUserId()}`).then(r => r.json())
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
        const params = new URLSearchParams({ category, subcategory, user_id: getCurrentUserId() })
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
                    ${item.content_type !== 'music' && item.summary ? buildCollapsibleSummary(item.summary, 'panel-item-summary') : ''}
                    ${tags.length ? `<div class="card-tags" style="margin-bottom:8px">${tags.map(t => `<span class="tag">#${t}</span>`).join('')}</div>` : ''}
                    <div class="panel-card-actions">
                        <a href="${item.url}" target="_blank" class="panel-item-link">링크 열기 &rarr;</a>
                        <div class="panel-move-wrap">
                            <button class="panel-move-btn" onclick="showPanelMoveDropdown(this, '${esc(item.id)}')">폴더 이동 ▾</button>
                            <div class="panel-move-dropdown"></div>
                        </div>
                        <button class="panel-delete-btn" onclick="panelDeleteItem('${esc(item.id)}', this)" title="삭제">🗑️</button>
                    </div>
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
        const data = await fetch(`/collections/${getCurrentUserId()}`).then(r => r.json())
        const sidebar = document.getElementById('left-sidebar')
        const list    = document.getElementById('group-list')

        if (!data.collections || !data.collections.length) {
            sidebar.classList.remove('open')
            return
        }
        sidebar.classList.add('open')
        list.innerHTML = `
            <div class="group-sidebar-add">
                <button class="sidebar-add-btn" onclick="showSidebarFolderInput(this)" title="새 폴더">＋</button>
            </div>
            ${data.collections.map(c => `
                <div class="group-sidebar-item" onclick="openCollectionPanel('${esc(c.id)}','${esc(c.name)}')">
                    <span class="group-sidebar-name">${c.emoji ? c.emoji + ' ' : ''}${c.name}</span>
                    <div class="sidebar-action-btns">
                        <button class="sidebar-emoji-btn" onclick="event.stopPropagation(); showEmojiPicker(this, '${esc(c.id)}')" title="이모티콘 변경">🎨</button>
                        <button class="sidebar-delete-btn" onclick="event.stopPropagation(); showFolderDeleteConfirm(this, '${esc(c.id)}', '${esc(c.name)}')" title="폴더 삭제">🗑️</button>
                    </div>
                </div>
            `).join('')}
        `
    } catch (e) {
        console.error('컬렉션 로드 실패:', e)
    }
}

window.showSidebarFolderInput = function(btn) {
    const wrap = btn.closest('.group-sidebar-add')
    if (wrap.querySelector('.sidebar-folder-input')) return
    btn.style.display = 'none'
    const input = document.createElement('input')
    input.type = 'text'
    input.className = 'sidebar-folder-input'
    input.placeholder = '폴더 이름'
    wrap.appendChild(input)
    input.focus()

    const done = async () => {
        const name = input.value.trim()
        if (name) {
            await fetch(`/collections?user_id=${getCurrentUserId()}&name=${encodeURIComponent(name)}`, { method: 'POST' })
            loadCollections()
        } else {
            input.remove()
            btn.style.display = ''
        }
    }
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter') done()
        if (e.key === 'Escape') { input.remove(); btn.style.display = '' }
    })
    input.addEventListener('blur', () => setTimeout(() => { if (document.contains(input)) { input.remove(); btn.style.display = '' } }, 150))
}

const EMOJI_LIST = ['📚','📝','🎵','🎬','🎮','💼','🍎','✈️','💡','📰','🎨','🏃','💰','📱','🔬','🌱','❤️','⭐','🔥','💎','🎯','🔑','🖥️','🎓','📷','🧪','🏠','🎁','📊','🍕','🎵','🎤','🏋️','📌','🗂️','🛒','🌍','🐾','🎪','🏆']

window.showFolderDeleteConfirm = function(btn, collectionId, collectionName) {
    document.querySelectorAll('.folder-delete-popup').forEach(p => p.remove())

    const popup = document.createElement('div')
    popup.className = 'folder-delete-popup'
    popup.innerHTML = `
        <div class="folder-delete-msg">'${collectionName}' 폴더를 삭제할까요?<br><span style="font-size:11px;color:#9A7055">콘텐츠는 사라지지 않아요</span></div>
        <div class="folder-delete-actions">
            <button class="folder-delete-cancel" onclick="this.closest('.folder-delete-popup').remove()">취소</button>
            <button class="folder-delete-confirm" onclick="deleteCollection('${esc(collectionId)}')">삭제</button>
        </div>
    `
    document.body.appendChild(popup)

    const rect = btn.getBoundingClientRect()
    popup.style.left = (rect.right + 8) + 'px'
    popup.style.top  = Math.min(rect.top, window.innerHeight - 120) + 'px'

    setTimeout(() => {
        document.addEventListener('click', function close(e) {
            if (!popup.contains(e.target) && e.target !== btn) {
                popup.remove()
                document.removeEventListener('click', close)
            }
        })
    }, 0)
}

window.deleteCollection = async function(collectionId) {
    document.querySelectorAll('.folder-delete-popup').forEach(p => p.remove())
    try {
        await fetch(`/collections/${collectionId}?user_id=${getCurrentUserId()}`, { method: 'DELETE' })
        loadCollections()
        loadTopFolders()
    } catch (e) {}
}

window.showEmojiPicker = function(btn, collectionId) {
    document.querySelectorAll('.emoji-picker-popup').forEach(p => p.remove())

    const picker = document.createElement('div')
    picker.className = 'emoji-picker-popup'
    picker.innerHTML = `
        <div class="emoji-picker-grid">
            ${EMOJI_LIST.map(e => `<button class="emoji-pick-btn" onclick="setCollectionEmoji('${collectionId}', '${e}')">${e}</button>`).join('')}
        </div>
        <button class="emoji-remove-btn" onclick="setCollectionEmoji('${collectionId}', null)">✕ 이모티콘 제거</button>
    `

    // body에 fixed로 붙여서 사이드바 레이아웃 영향 없앰
    document.body.appendChild(picker)

    // 버튼 위치 기준으로 팝업 좌표 계산
    const rect = btn.getBoundingClientRect()
    const pickerW = 232
    let left = rect.right + 8
    if (left + pickerW > window.innerWidth) left = rect.left - pickerW - 8
    picker.style.left = left + 'px'
    picker.style.top  = Math.min(rect.top, window.innerHeight - 280) + 'px'

    setTimeout(() => {
        document.addEventListener('click', function closePicker(e) {
            if (!picker.contains(e.target) && e.target !== btn) {
                picker.remove()
                document.removeEventListener('click', closePicker)
            }
        })
    }, 0)
}

window.setCollectionEmoji = async function(collectionId, emoji) {
    document.querySelectorAll('.emoji-picker-popup').forEach(p => p.remove())
    try {
        await fetch(`/collections/${collectionId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: getCurrentUserId(), emoji: emoji || null })
        })
        loadCollections()
    } catch (e) {}
}

// ── 컬렉션 상세 패널 열기 ──
async function openCollectionPanel(collectionId, name) {
    openRightPanel(name, '<div class="chat-loading">···</div>')
    try {
        const data = await fetch(`/api/collections/${collectionId}/items?user_id=${getCurrentUserId()}`).then(r => r.json())
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
                    <div class="panel-card-actions">
                        <a href="${item.url}" target="_blank" class="panel-item-link">링크 열기 &rarr;</a>
                        <div class="panel-move-wrap">
                            <button class="panel-move-btn" onclick="showPanelMoveDropdown(this, '${esc(item.id)}')">폴더 이동 ▾</button>
                            <div class="panel-move-dropdown"></div>
                        </div>
                        <button class="panel-delete-btn" onclick="panelDeleteItem('${esc(item.id)}', this)" title="삭제">🗑️</button>
                    </div>
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
    // currentContentId는 세션 간 유지 (저장 후 마감 수정 흐름)

    let chatPanelCollectionId   = selectedCollectionId
    let chatPanelCollectionName = selectedCollectionName

    openRightPanel('AI 어시스턴트', `
        <div class="chat-container">
            <div class="chat-messages" id="chat-messages">
                <div class="chat-msg ai">안녕하세요! URL을 붙여넣으면 저장하고, 그 외 메시지는 AI와 대화할 수 있어요.</div>
            </div>
            <div class="chat-folder-row" id="chat-folder-row">
                <span class="chat-folder-label">폴더:</span>
                <button class="chat-folder-btn ${chatPanelCollectionId ? 'active' : ''}" id="chat-folder-btn">
                    ${chatPanelCollectionId ? '📁 ' + chatPanelCollectionName : '📁 선택 안 함'}
                </button>
                <div class="chat-folder-dropdown folder-dropdown" id="chat-folder-dropdown"></div>
                <button class="chat-reset-btn" id="chat-reset-btn" title="대화 초기화">↺</button>
            </div>
            <div class="chat-input-wrap">
                <input type="text" id="chat-input" class="chat-input" placeholder="URL 붙여넣기 또는 메시지 입력" />
                <button id="chat-send" class="chat-send-btn">&#8594;</button>
            </div>
        </div>
    `, true)

    // 채팅 패널 내 폴더 선택
    const chatFolderBtn      = document.getElementById('chat-folder-btn')
    const chatFolderDropdown = document.getElementById('chat-folder-dropdown')

    chatFolderBtn.addEventListener('click', async (e) => {
        e.stopPropagation()
        if (chatFolderDropdown.classList.contains('open')) {
            chatFolderDropdown.classList.remove('open')
            return
        }
        await populateFolderDropdown(chatFolderDropdown, (id, name) => {
            chatPanelCollectionId   = id
            chatPanelCollectionName = name
            // 메인 상태도 동기화
            selectedCollectionId   = id
            selectedCollectionName = name
            chatFolderBtn.textContent = id ? `📁 ${name}` : '📁 선택 안 함'
            chatFolderBtn.classList.toggle('active', !!id)
            chatFolderDropdown.classList.remove('open')
            // 메인 버튼도 동기화
            const mainBtn = document.getElementById('folder-picker-btn')
            if (mainBtn) {
                mainBtn.textContent = id ? `📁 ${name}` : '📁'
                mainBtn.classList.toggle('active', !!id)
            }
        })
        chatFolderDropdown.classList.add('open')
    })

    document.addEventListener('click', () => chatFolderDropdown.classList.remove('open'))

    document.getElementById('chat-reset-btn').addEventListener('click', () => {
        chatHistory = []
        shownIds = new Set()
        const msgs = document.getElementById('chat-messages')
        if (msgs) msgs.innerHTML = '<div class="chat-msg ai">대화가 초기화됐어요. 새로 질문해주세요!</div>'
    })

    const chatInput = document.getElementById('chat-input')
    const chatSend  = document.getElementById('chat-send')

    const doSend = () => sendChat(chatPanelCollectionId)
    chatSend.addEventListener('click', doSend)
    chatInput.addEventListener('keydown', e => { if (e.key === 'Enter') doSend() })
    chatInput.focus()

    if (initialText) {
        chatInput.value = initialText
        setTimeout(doSend, 60)
    }
}

// ── 채팅 메시지 전송 (URL → 저장 / 텍스트 → AI 대화) ──
async function sendChat(chatCollectionId) {
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
        const urlMatches = text.match(/https?:\/\/[^\s]+/gi) || []
        if (urlMatches.length > 0) {
            // URL → 저장 (단일 또는 복수)
            const deadlineMatch = text.match(/마감[：:]\s*(\d{4}-\d{2}-\d{2})/)
            const deadline = deadlineMatch ? deadlineMatch[1] : null
            const instruction = deadline ? `마감기한: ${deadline}` : ''
            const urls = urlMatches
            loadingEl.textContent = urls.length > 1 ? `0 / ${urls.length} 저장 중···` : '···'

            let savedCount = 0
            for (const url of urls) {
                const res = await fetch('/ingest', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        url,
                        user_id: getCurrentUserId(),
                        instruction,
                        collection_id: chatCollectionId || null,
                    })
                })
                const data = await res.json()
                if (!res.ok || data.error) {
                    const errEl = document.createElement('div')
                    errEl.className = 'chat-msg ai'
                    errEl.textContent = `저장 실패: ${url}`
                    chatMessages.appendChild(errEl)
                    continue
                }

                if (!data.duplicate && data.id) currentContentId = data.id
                savedCount++
                if (urls.length > 1) loadingEl.textContent = `${savedCount} / ${urls.length} 저장 중···`

                const aiEl = document.createElement('div')
                aiEl.className = 'chat-msg ai'

                if (data.duplicate) {
                    aiEl.innerHTML = buildSavedItemContent(data.content, true, null)
                    chatMessages.appendChild(aiEl)
                } else {
                    aiEl.innerHTML = buildSavedItemContent(data, false, urls.length === 1 ? data.deadline_confirmation : null)
                    chatMessages.appendChild(aiEl)
                    if (data.reminder_message && urls.length === 1) {
                        const reminderEl = document.createElement('div')
                        reminderEl.className = 'chat-msg ai'
                        const similar = data.similar_contents || []
                        reminderEl.innerHTML = data.reminder_message
                            + (similar.length ? buildResultCards(similar) : '')
                        chatMessages.appendChild(reminderEl)
                    }
                }
                chatMessages.scrollTop = chatMessages.scrollHeight
            }

            loadingEl.remove()
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
                    user_id: getCurrentUserId(),
                    history: chatHistory.slice(-10),
                    shown_ids: [...shownIds],
                    content_id: currentContentId,  // 마감기한 수정 대상 ID
                })
            })
            const data = await res.json()
            loadingEl.remove()

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
function buildSavedItemContent(item, isDuplicate = false, deadlineConfirmation = null) {
    const tags = Array.isArray(item.tags) ? item.tags : (item.tags ? JSON.parse(item.tags) : [])
    const thumbHTML = item.thumbnail
        ? `<img src="${item.thumbnail}" style="width:100%;height:140px;object-fit:cover;border-radius:8px;margin-bottom:10px;display:block" onerror="this.style.display='none'" alt="" />`
        : ''
    const statusText  = isDuplicate ? '이미 저장된 콘텐츠예요' : '✓ 저장 완료'
    const statusColor = isDuplicate ? '#9A7055' : '#5A9A60'
    const summary = item.one_line_summary || item.description || ''
    const subcat  = item.sub_category || item.subcategory || ''

    const deadlineHTML = deadlineConfirmation ? `
        <div class="deadline-confirm-box">
            <span class="deadline-confirm-msg">${deadlineConfirmation}</span>
            <div class="deadline-confirm-btns">
                <button class="dc-btn dc-ok" onclick="dismissDeadlineConfirm(this)">맞아요 ✓</button>
                <button class="dc-btn dc-edit" onclick="editDeadline(this)">날짜 수정</button>
            </div>
        </div>
    ` : ''

    return `
        <div style="font-size:11px;font-weight:700;color:${statusColor};margin-bottom:8px;letter-spacing:0.3px">${statusText}</div>
        ${thumbHTML}
        <div style="font-size:14px;font-weight:600;color:#2C1A0E;margin-bottom:4px;line-height:1.4">${item.title}</div>
        <div style="font-size:12px;color:#9A7055;margin-bottom:8px">${item.category || ''}${subcat ? ' / ' + subcat : ''}</div>
        ${summary ? `<div style="font-size:13px;color:#6B4E3A;line-height:1.55;margin-bottom:8px">${summary}</div>` : ''}
        ${tags.length ? `<div class="card-tags" style="margin-bottom:8px">${tags.map(t => `<span class="tag">#${t}</span>`).join('')}</div>` : ''}
        <a href="${item.url}" target="_blank" class="panel-item-link" style="margin-top:4px;display:inline-block">링크 열기 &rarr;</a>
        ${deadlineHTML}
    `
}

// 마감기한 확인 버튼 핸들러
window.dismissDeadlineConfirm = function(btn) {
    btn.closest('.deadline-confirm-box').remove()
}

window.editDeadline = function(btn) {
    btn.closest('.deadline-confirm-box').remove()
    const chatInput = document.getElementById('chat-input')
    if (chatInput) {
        chatInput.placeholder = '마감일을 알려주세요. 예: "마감 없어" 또는 "7월 15일이야"'
        chatInput.focus()
    }
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
        const thumb   = item.thumbnail_url || item.thumbnail || ''
        const thumbHTML = thumb
            ? `<img class="msg-card-thumb" src="${thumb}" onerror="this.style.display='none'" alt="" />`
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

// 삭제 확인 UI 빌드
function buildDeleteConfirm(items, ids) {
    const checkboxes = items.map(item => `
        <label class="confirm-item-row">
            <input type="checkbox" class="delete-check" value="${item.id}" checked />
            <span>${item.title}</span>
        </label>
    `).join('')
    return `
        <div class="confirm-box delete-confirm-box">
            <div class="confirm-items">${checkboxes}</div>
            <div class="confirm-actions">
                <button class="confirm-btn confirm-cancel" onclick="this.closest('.confirm-box').remove()">취소</button>
                <button class="confirm-btn confirm-delete" onclick="executeDelete(this)">선택 항목 삭제</button>
            </div>
        </div>
    `
}

// 이동 확인 UI 빌드
function buildMoveConfirm(items, ids, targetFolder) {
    const titleList = items.map(i => `<div class="confirm-item-title">${i.title}</div>`).join('')
    return `
        <div class="confirm-box move-confirm-box"
             data-ids="${ids.join(',')}"
             data-folder="${esc(targetFolder)}">
            <div class="confirm-items">${titleList}</div>
            <div class="confirm-actions">
                <button class="confirm-btn confirm-cancel" onclick="this.closest('.confirm-box').remove()">취소</button>
                <button class="confirm-btn confirm-move" onclick="executeMove(this)">'${targetFolder}'으로 이동</button>
            </div>
        </div>
    `
}

window.executeDelete = async function(btn) {
    const box    = btn.closest('.confirm-box')
    const checks = box.querySelectorAll('.delete-check:checked')
    const ids    = [...checks].map(c => c.value)
    if (!ids.length) return

    btn.disabled = true
    btn.textContent = '삭제 중···'

    let successCount = 0
    for (const id of ids) {
        try {
            const res = await fetch(`/contents/${id}?user_id=${getCurrentUserId()}`, { method: 'DELETE' })
            if (res.ok) successCount++
        } catch (e) {}
    }

    box.innerHTML = `<div style="padding:8px;color:#5A9A60;font-size:13px;font-weight:600">✓ ${successCount}개 삭제 완료</div>`
    setTimeout(() => { box.remove(); loadTopFolders(); loadCollections() }, 1500)
}

window.executeMove = async function(btn) {
    const box    = btn.closest('.confirm-box')
    const ids    = box.dataset.ids.split(',').filter(Boolean)
    const folder = box.dataset.folder

    btn.disabled = true
    btn.textContent = '이동 중···'

    try {
        const res = await fetch('/contents/move', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: getCurrentUserId(),
                content_ids: ids,
                target_folder: folder,
            })
        })
        if (res.ok) {
            box.innerHTML = `<div style="padding:8px;color:#5A9A60;font-size:13px;font-weight:600">✓ '${folder}' 폴더로 이동 완료</div>`
            setTimeout(() => { box.remove(); loadCollections() }, 1500)
        } else {
            throw new Error('이동 실패')
        }
    } catch (e) {
        btn.disabled = false
        btn.textContent = `'${folder}'으로 이동`
        appendMsg(document.getElementById('chat-messages') || document.body, 'ai', '이동에 실패했어요. 다시 시도해주세요.')
    }
}

// 폴더 생성 확인 UI 빌드
function buildFolderConfirm(confirmationData) {
    const newName   = confirmationData.new_folder_name || ''
    const suggested = confirmationData.suggested_folder

    if (suggested) {
        return `
            <div class="confirm-box folder-confirm-box">
                <div class="confirm-actions" style="flex-direction:column;gap:8px;align-items:stretch;">
                    <button class="confirm-btn confirm-move" onclick="createFolder('${esc(suggested)}')">기존 '${suggested}' 폴더 사용</button>
                    <button class="confirm-btn confirm-cancel" onclick="createFolder('${esc(newName)}')">새로 '${newName}' 만들기</button>
                </div>
            </div>
        `
    }
    return `
        <div class="confirm-box folder-confirm-box">
            <div class="confirm-actions">
                <button class="confirm-btn confirm-cancel" onclick="this.closest('.confirm-box').remove()">취소</button>
                <button class="confirm-btn confirm-move" onclick="createFolder('${esc(newName)}')">'${newName}' 만들기</button>
            </div>
        </div>
    `
}

window.createFolder = async function(name) {
    document.querySelector('.folder-confirm-box')?.remove()
    try {
        const res = await fetch(`/collections?user_id=${getCurrentUserId()}&name=${encodeURIComponent(name)}`, { method: 'POST' })
        const chatMessages = document.getElementById('chat-messages')
        if (chatMessages) {
            const el = document.createElement('div')
            el.className = 'chat-msg ai'
            el.textContent = res.ok ? `'${name}' 폴더를 만들었어요!` : `폴더 생성에 실패했어요.`
            chatMessages.appendChild(el)
            chatMessages.scrollTop = chatMessages.scrollHeight
        }
        if (res.ok) loadCollections()
    } catch (e) {}
}

// 폴더 선택 이동 UI (target 없을 때)
function buildFolderPickForMove(items, ids) {
    const uid = Date.now()
    const titleList = items.slice(0, 3).map(i => `<div class="confirm-item-title">${i.title}</div>`).join('')
    const more = items.length > 3 ? `<div style="font-size:11px;color:#9A7055;margin-top:2px">외 ${items.length - 3}개</div>` : ''
    return `
        <div class="confirm-box move-folder-pick-box" data-ids="${ids.join(',')}">
            <div class="confirm-items">${titleList}${more}</div>
            <select class="folder-pick-select" id="fps-${uid}">
                <option value="">폴더 선택...</option>
            </select>
            <div class="confirm-actions" style="margin-top:8px">
                <button class="confirm-btn confirm-cancel" onclick="this.closest('.confirm-box').remove()">취소</button>
                <button class="confirm-btn confirm-move" onclick="executeMoveWithPicker(this, 'fps-${uid}')">이동</button>
            </div>
        </div>
    `
}

async function populateFolderPickSelect(selectId) {
    const sel = document.getElementById(selectId)
    if (!sel) return
    try {
        const [colData, subData] = await Promise.all([
            fetch(`/collections/${getCurrentUserId()}`).then(r => r.json()),
            fetch(`/api/categories?user_id=${getCurrentUserId()}`).then(r => r.json()),
        ])
        const cols = colData.collections || []
        if (cols.length) {
            const grp = document.createElement('optgroup')
            grp.label = '내 폴더'
            cols.forEach(c => {
                const opt = document.createElement('option')
                opt.value = 'col::' + c.name
                opt.textContent = (c.emoji ? c.emoji + ' ' : '') + c.name
                grp.appendChild(opt)
            })
            sel.appendChild(grp)
        }
        // 소분류 추출
        const subs = []
        Object.entries(subData).forEach(([cat, list]) => {
            list.forEach(s => subs.push({ cat, name: s.name }))
        })
        if (subs.length) {
            const grp = document.createElement('optgroup')
            grp.label = '카테고리 (자동분류)'
            subs.forEach(s => {
                const opt = document.createElement('option')
                opt.value = 'sub::' + s.name
                opt.textContent = s.cat + ' / ' + s.name
                grp.appendChild(opt)
            })
            sel.appendChild(grp)
        }
    } catch (e) {}
}

window.executeMoveWithPicker = async function(btn, selectId) {
    const sel = document.getElementById(selectId)
    const val = sel ? sel.value : ''
    if (!val) { alert('폴더를 선택해주세요.'); return }
    const box = btn.closest('.confirm-box')
    const ids = box.dataset.ids.split(',').filter(Boolean)
    const [type, name] = val.split('::')
    btn.disabled = true
    btn.textContent = '이동 중···'
    try {
        let ok = false
        if (type === 'col') {
            const res = await fetch('/contents/move', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: getCurrentUserId(), content_ids: ids, target_folder: name })
            })
            ok = res.ok
        } else {
            // 소분류 변경 (여러 개면 순차 처리)
            const results = await Promise.all(ids.map(id =>
                fetch(`/contents/${id}/subcategory`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: getCurrentUserId(), sub_category: name })
                })
            ))
            ok = results.every(r => r.ok)
        }
        if (ok) {
            box.innerHTML = `<div style="padding:8px;color:#5A9A60;font-size:13px;font-weight:600">✓ '${name}'(으)로 이동 완료</div>`
            setTimeout(() => { box.remove(); loadCollections(); loadTopFolders() }, 1500)
        } else throw new Error()
    } catch (e) { btn.disabled = false; btn.textContent = '이동' }
}

window.panelDeleteItem = async function(contentId, btn) {
    const card = btn.closest('.panel-item-card, .archive-item-card')
    const title = card?.querySelector('.panel-item-title, .archive-item-title')?.textContent || '이 항목'

    if (!confirm(`'${title}'\n\n정말 삭제할까요?`)) return

    btn.disabled = true
    try {
        const res = await fetch(`/contents/${contentId}?user_id=${getCurrentUserId()}`, { method: 'DELETE' })
        if (res.ok) {
            card?.remove()
        } else {
            throw new Error()
        }
    } catch (e) {
        alert('삭제에 실패했어요. 다시 시도해주세요.')
        btn.disabled = false
    }
}

window._mergePending = {}

function buildMergePicker(data) {
    const uid = 'mp-' + Date.now()
    const cats = data.merge_categories || []
    const target = data.merge_target || ''

    window._mergePending[uid] = {
        ids: data.pending_move_ids || [],
        subCategory: target,
    }

    const opts = cats.map(cat =>
        `<option value="cat::${cat}">${cat} &gt; ${target}</option>`
    ).join('')

    return `
        <div class="merge-picker-wrap" id="${uid}-wrap">
            <select class="folder-pick-select" id="${uid}-sel">
                <option value="">분류 선택...</option>
                ${opts}
                <option value="new::${target}">+ 새 폴더 만들기 (${target})</option>
            </select>
            <button class="chat-action-btn" onclick="executeMerge('${uid}')">합치기</button>
        </div>`
}

window.executeMerge = async function(uid) {
    const pending = window._mergePending[uid]
    if (!pending) return alert('데이터를 찾을 수 없어요.')

    const sel = document.getElementById(uid + '-sel')
    const val = sel?.value
    if (!val) return alert('분류를 선택해주세요.')

    const { ids, subCategory } = pending
    const wrap = document.getElementById(uid + '-wrap')
    const userId = getCurrentUserId()

    try {
        if (val.startsWith('new::')) {
            const name = val.replace('new::', '')
            const collRes = await fetch(`/collections?user_id=${userId}&name=${encodeURIComponent(name)}`, { method: 'POST' })
            if (!collRes.ok) throw new Error()
            const coll = await collRes.json()
            await Promise.all(ids.map(id =>
                fetch('/contents/move', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ content_id: id, collection_id: coll.id, user_id: userId })
                })
            ))
            if (wrap) wrap.innerHTML = `<div style="padding:8px;color:#5A9A60;font-size:13px;font-weight:600">✓ '${name}' 새 폴더로 합쳤어요!</div>`
        } else {
            const newCategory = val.replace('cat::', '')
            const res = await fetch('/contents/batch/category', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, content_ids: ids, category: newCategory })
            })
            if (!res.ok) throw new Error()
            if (wrap) wrap.innerHTML = `<div style="padding:8px;color:#5A9A60;font-size:13px;font-weight:600">✓ '${newCategory} &gt; ${subCategory}'로 합쳤어요!</div>`
        }
        delete window._mergePending[uid]
        setTimeout(() => loadCollections(), 1000)
    } catch (e) {
        alert('합치기에 실패했어요. 다시 시도해주세요.')
    }
}

// AI 응답 HTML 빌드 (삭제/이동/폴더 확인 UI 포함)
function buildAIContent(data) {
    let html = data.answer ? `<div>${data.answer}</div>` : ''

    if (data.results && data.results.length) {
        html += buildResultCards(data.results)
    }

    // 합치기 UI
    if (data.merge_mode && data.pending_move_ids && data.pending_move_ids.length) {
        html += buildMergePicker(data)
    }

    // 폴더 선택 이동 (target 없는 경우)
    if (!data.merge_mode && data.needs_folder_pick && data.pending_move_ids && data.pending_move_ids.length) {
        const pickId = 'fps-' + Date.now()
        html += buildFolderPickForMove(data.results || [], data.pending_move_ids).replace(/fps-\d+/g, pickId)
        setTimeout(() => populateFolderPickSelect(pickId), 0)
    }

    // 폴더 생성 확인
    if (data.needs_confirmation && data.confirmation_data) {
        html += buildFolderConfirm(data.confirmation_data)
    }

    // 삭제 확인
    if (data.needs_confirmation && data.pending_delete_ids && data.pending_delete_ids.length) {
        html += buildDeleteConfirm(data.results || [], data.pending_delete_ids)
    }

    // 이동 확인
    if (data.needs_confirmation && data.pending_move_ids && data.pending_move_ids.length) {
        html += buildMoveConfirm(data.results || [], data.pending_move_ids, data.target_folder || '')
    }

    if (data.follow_up_questions && data.follow_up_questions.length) {
        html += `<div class="follow-up-questions">${data.follow_up_questions.map(q =>
            `<button class="follow-up-btn" onclick="followUp(this)">${q}</button>`
        ).join('')}</div>`
    }

    return html
}

window.showPanelMoveDropdown = async function(btn, contentId) {
    const wrap = btn.closest('.panel-move-wrap')
    const dropdown = wrap.querySelector('.panel-move-dropdown')

    if (dropdown.classList.contains('open')) {
        dropdown.classList.remove('open')
        dropdown.innerHTML = ''
        return
    }

    dropdown.innerHTML = '<div style="padding:6px 10px;font-size:12px;color:#9A7055">불러오는 중···</div>'
    dropdown.classList.add('open')

    try {
        const [colData, subData] = await Promise.all([
            fetch(`/collections/${getCurrentUserId()}`).then(r => r.json()),
            fetch(`/api/categories?user_id=${getCurrentUserId()}`).then(r => r.json()),
        ])
        const cols = colData.collections || []
        const subs = []
        Object.entries(subData).forEach(([cat, list]) => list.forEach(s => subs.push({ cat, name: s.name })))

        let html = ''
        if (cols.length) {
            html += `<div class="panel-move-group-label">내 폴더</div>`
            html += cols.map(c => `
                <div class="panel-move-option" data-type="col" data-name="${esc(c.name)}" onclick="executePanelMove('${esc(contentId)}', this)">
                    ${c.emoji ? c.emoji + ' ' : ''}${c.name}
                </div>`).join('')
        }
        if (subs.length) {
            html += `<div class="panel-move-group-label">카테고리</div>`
            html += subs.map(s => `
                <div class="panel-move-option" data-type="sub" data-name="${esc(s.name)}" onclick="executePanelMove('${esc(contentId)}', this)">
                    ${s.cat} / ${s.name}
                </div>`).join('')
        }
        dropdown.innerHTML = html || '<div style="padding:6px 10px;font-size:12px;color:#9A7055">없음</div>'
    } catch (e) {
        dropdown.innerHTML = '<div style="padding:6px 10px;font-size:12px;color:#C0392B">불러오기 실패</div>'
    }

    setTimeout(() => {
        document.addEventListener('click', function close(e) {
            if (!wrap.contains(e.target)) {
                dropdown.classList.remove('open')
                dropdown.innerHTML = ''
                document.removeEventListener('click', close)
            }
        })
    }, 0)
}

window.executePanelMove = async function(contentId, optionEl) {
    const type = optionEl.dataset.type
    const name = optionEl.dataset.name
    const dropdown = optionEl.closest('.panel-move-dropdown')
    dropdown.innerHTML = '<div style="padding:6px 10px;font-size:12px;color:#9A7055">이동 중···</div>'
    try {
        let res
        if (type === 'col') {
            res = await fetch('/contents/move', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: getCurrentUserId(), content_ids: [contentId], target_folder: name })
            })
        } else {
            res = await fetch(`/contents/${contentId}/subcategory`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: getCurrentUserId(), sub_category: name })
            })
        }
        if (res.ok) {
            dropdown.classList.remove('open')
            dropdown.innerHTML = ''
            const card = optionEl.closest('.panel-item-card') || dropdown.closest('.panel-item-card')
            if (card) { card.style.opacity = '0.4'; setTimeout(() => card.remove(), 600) }
            loadCollections(); loadTopFolders()
        }
    } catch (e) { dropdown.classList.remove('open') }
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
    archiveData     = await fetch(`/api/categories?user_id=${getCurrentUserId()}`).then(r => r.json())
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
            </span>
        </div>`
}

function renderArchiveCats(query) {
    const el = document.getElementById('archive-cat-list')
    if (!el) return
    const q = query.toLowerCase().trim()
    let html = '', hasAny = false

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
    const params = new URLSearchParams({ category, subcategory, user_id: getCurrentUserId() })
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

window.deleteArchiveContent = async function(contentId, category, subcategory) {
    if (!confirm('이 콘텐츠를 영구 삭제할까요?')) return
    try {
        const res = await fetch(`/contents/${contentId}?user_id=${getCurrentUserId()}`, { method: 'DELETE' })
        if (!res.ok) throw new Error('삭제 실패')
        showArchiveItems(category, subcategory)
        loadTopFolders()
    } catch (e) { alert('삭제 실패: ' + e.message) }
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

document.getElementById('btn-reminders').addEventListener('click', async () => {
    const data = await fetch(`/deadlines/${getCurrentUserId()}`).then(r => r.json())
    if (!data.deadlines || !data.deadlines.length) {
        openModal('리마인더', '<p class="no-result">마감 자료가 없어요.</p>')
        return
    }
    const now = new Date()
    calYear      = now.getFullYear()
    calMonth     = now.getMonth()
    calDeadlines = data.deadlines
    calSelectedDate = null
    renderReminderCalendar()
})

function renderReminderCalendar() {
    const MONTHS = ['1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월']
    const todayStr = new Date().toISOString().slice(0, 10)
    const monthPad = String(calMonth + 1).padStart(2, '0')

    const dateMap = {}
    calDeadlines.forEach(r => {
        if (r.deadline_date) {
            if (!dateMap[r.deadline_date]) dateMap[r.deadline_date] = []
            dateMap[r.deadline_date].push(r)
        }
    })

    const firstDow    = new Date(calYear, calMonth, 1).getDay()
    const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate()
    const weekdays    = ['일','월','화','수','목','금','토']

    let cellsHTML = weekdays.map((d, i) =>
        `<div class="cal-weekday ${i===0?'sun':i===6?'sat':''}">${d}</div>`
    ).join('')

    const prevDays = new Date(calYear, calMonth, 0).getDate()
    for (let i = firstDow - 1; i >= 0; i--)
        cellsHTML += `<div class="cal-cell other-month"><div class="cal-dots"></div><div class="cal-date-num">${prevDays - i}</div></div>`

    for (let d = 1; d <= daysInMonth; d++) {
        const dateStr = `${calYear}-${monthPad}-${String(d).padStart(2,'0')}`
        const dow   = (firstDow + d - 1) % 7
        const items = dateMap[dateStr] || []
        const dots  = Array(Math.min(items.length, 4)).fill('<div class="cal-dot"></div>').join('')
        const cls   = [dateStr === todayStr ? 'today' : '', dow === 0 ? 'sunday' : '', dow === 6 ? 'saturday' : ''].join(' ')
        const isSel = dateStr === calSelectedDate ? 'selected' : ''
        cellsHTML += `
            <div class="cal-cell ${cls} ${isSel}" onclick="window.calSelectDate('${dateStr}')">
                <div class="cal-dots">${dots}</div>
                <div class="cal-date-num">${d}</div>
            </div>`
    }

    const total    = firstDow + daysInMonth
    const trailing = total % 7 === 0 ? 0 : 7 - (total % 7)
    for (let i = 1; i <= trailing; i++)
        cellsHTML += `<div class="cal-cell other-month"><div class="cal-dots"></div><div class="cal-date-num">${i}</div></div>`

    const monthStart = `${calYear}-${monthPad}-01`
    const monthEnd   = `${calYear}-${monthPad}-${String(daysInMonth).padStart(2,'0')}`
    const listItems  = calSelectedDate
        ? calDeadlines.filter(r => r.deadline_date === calSelectedDate)
        : calDeadlines
            .filter(r => r.deadline_date >= monthStart && r.deadline_date <= monthEnd)
            .sort((a, b) => a.deadline_date.localeCompare(b.deadline_date))

    const filterBarHTML = calSelectedDate ? `
        <div class="cal-filter-bar">
            <span>📌 ${calSelectedDate} 마감 콘텐츠</span>
            <button class="cal-filter-clear" onclick="window.calClearFilter()">전체 보기 ✕</button>
        </div>` : ''

    const noMsg = calSelectedDate ? '이 날 마감 콘텐츠가 없어요.' : '이 달에 마감 자료가 없어요.'
    const eventListHTML = filterBarHTML + (listItems.length
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

    openModal('리마인더', `
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
        </div>`)
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

window.toggleDeadlineEdit = function(id, date, note) {
    const form = document.getElementById('ref-' + id)
    if (!form) return
    const isOpen = form.style.display !== 'none'
    form.style.display = isOpen ? 'none' : 'block'
    if (!isOpen && date) {
        document.getElementById('rdi-' + id).value = date
        document.getElementById('rni-' + id).value = note || ''
    }
}

window.saveDeadlineEdit = async function(id) {
    const dateVal = document.getElementById('rdi-' + id)?.value
    const noteVal = document.getElementById('rni-' + id)?.value
    if (!dateVal) return alert('날짜를 선택해주세요.')
    try {
        const res = await fetch(`/deadlines/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: getCurrentUserId(), deadline_date: dateVal, deadline_note: noteVal })
        })
        if (!res.ok) throw new Error()
        const row = document.querySelector(`#ri-${id} .reminder-deadline`)
        if (row) row.textContent = '마감: ' + dateVal
        const cat = document.querySelector(`#ri-${id} .reminder-cat`)
        if (cat && noteVal) cat.textContent = noteVal
        document.getElementById('ref-' + id).style.display = 'none'
    } catch (e) { alert('수정에 실패했어요.') }
}

window.removeDeadline = async function(id) {
    if (!confirm('마감일을 삭제할까요?')) return
    try {
        const res = await fetch(`/deadlines/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: getCurrentUserId(), remove: true })
        })
        if (!res.ok) throw new Error()
        document.getElementById('ri-' + id)?.remove()
    } catch (e) { alert('삭제에 실패했어요.') }
}

document.getElementById('btn-reclassify').addEventListener('click', async () => {
    const btn = document.getElementById('btn-reclassify')
    btn.disabled = true
    btn.textContent = '재분류 중···'
    try {
        const res  = await fetch(`/admin/reclassify/${getCurrentUserId()}`, { method: 'POST' })
        const data = await res.json()
        alert(`재분류 완료! ${data.updated}개 업데이트, ${data.failed}개 실패`)
        loadTopFolders()
        loadCollections()
    } catch (e) {
        alert('재분류 실패: ' + e.message)
    } finally {
        btn.disabled = false
        btn.textContent = '재분류'
    }
})

document.getElementById('btn-report').addEventListener('click', () => {
    const overlay = document.createElement('div')
    overlay.id = 'monthly-report-overlay'
    overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:#fdf8f5;'
    overlay.innerHTML = `
        <button onclick="document.getElementById('monthly-report-overlay').remove()"
            style="position:fixed;top:16px;right:20px;z-index:10000;background:#6b3a2a;color:#fdf3ec;border:none;border-radius:20px;padding:8px 20px;font-size:14px;font-weight:700;cursor:pointer;">
            ✕ 닫기
        </button>
        <iframe src="/monthly-report?user_id=${getCurrentUserId()}" style="width:100%;height:100%;border:none;display:block;"></iframe>
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
        <iframe src="/weekly-report?user_id=${getCurrentUserId()}" style="width:100%;height:100%;border:none;display:block;"></iframe>
    `
    document.body.appendChild(overlay)
})

// ── 초기 로드 ──
initAuth()
if (isLoggedIn()) {
    loadTopFolders()
    loadCollections()
}
initFolderPicker()
