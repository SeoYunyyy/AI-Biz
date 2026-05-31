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
        const data = await fetch(`/collections/${getCurrentUserId()}`).then(r => r.json())
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

// AI 응답 HTML 빌드 (삭제/이동/폴더 확인 UI 포함)
function buildAIContent(data) {
    let html = data.answer ? `<div>${data.answer}</div>` : ''

    if (data.results && data.results.length) {
        html += buildResultCards(data.results)
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
    const data = await fetch(`/api/categories?user_id=${getCurrentUserId()}`).then(r => r.json())
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
    const params = new URLSearchParams({ category, subcategory, user_id: getCurrentUserId() })
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

document.getElementById('btn-reminders').addEventListener('click', async () => {
    const data = await fetch(`/deadlines/${getCurrentUserId()}`).then(r => r.json())
    if (!data.deadlines || !data.deadlines.length) {
        openModal('리마인더', '<p class="no-result">마감 자료가 없어요.</p>')
        return
    }
    openModal('리마인더', data.deadlines.map(r => `
        <div class="reminder-item">
            <span class="reminder-deadline">마감: ${r.deadline_date}</span>
            <p class="reminder-title">${r.title}</p>
            ${r.deadline_note ? `<span class="reminder-cat">${r.deadline_note}</span>` : ''}
            <a href="${r.url}" target="_blank" class="card-link">링크 열기 &rarr;</a>
        </div>
    `).join(''))
})

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
initAuth()
if (isLoggedIn()) {
    loadTopFolders()
    loadCollections()
}
initFolderPicker()
