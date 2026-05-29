// ── Keepit 메인 인터랙션 ──

const promptInput   = document.getElementById('prompt-input')
const submitBtn     = document.getElementById('submit-btn')
const resultsDiv    = document.getElementById('results')
const modal         = document.getElementById('modal')
const modalBody     = document.getElementById('modal-body')
const rightPanel    = document.getElementById('right-panel')
const panelBody     = document.getElementById('panel-body')
const panelTitle    = document.getElementById('panel-title')
const leftSidebar   = document.getElementById('left-sidebar')
const groupList     = document.getElementById('group-list')
const groupEditModal = document.getElementById('group-edit-modal')

// 수정 모달 데이터 임시 저장소 (onclick 속성에 JSON 직렬화 없이 참조)
const editStore = {}
let editStoreSeq = 0
let editGroupId   = null
let editGroupItems = []

// 채팅 전역 상태 (접어도 유지)
let chatHistory    = []   // [{role, content}] — API 전송용
let chatDomMsgs    = []   // [{role, html}]    — DOM 재빌드용
let chatPanelOpen  = false

// 현재 활성 컨텍스트 — LLM이 "지금 사용자가 뭘 보고 있는지" 알게 함
let activeContext  = {
    type:  null,    // 'group' | 'search' | null
    group: null,    // {id, name}
    items: [],      // 현재 컨텍스트의 아이템 목록
}

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

// 결과 카드 HTML 생성
function buildCard(item, isSaved = false) {
    const showSummary = item.content_type !== 'music' && item.summary
    const tags = Array.isArray(item.tags) ? item.tags : (item.tags ? JSON.parse(item.tags) : [])
    return `
        <div class="result-card">
            ${isSaved ? '<span class="save-banner">저장 완료</span>' : ''}
            <span class="card-meta">${item.category} &nbsp;/&nbsp; ${item.subcategory}</span>
            <p class="card-title">${item.title}</p>
            ${showSummary ? `<p class="card-summary">${item.summary}</p>` : ''}
            ${tags.length ? `<div class="card-tags">${tags.map(t => `<span class="tag">#${t}</span>`).join('')}</div>` : ''}
            <a href="${item.url}" target="_blank" class="card-link">링크 열기 &rarr;</a>
        </div>
    `
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

// ── 그룹 목록 로드 (좌측 사이드바) ──
async function loadGroups() {
    try {
        const data = await fetch('/api/groups').then(r => r.json())
        if (!data.groups.length) {
            leftSidebar.classList.remove('open')
            return
        }
        leftSidebar.classList.add('open')
        groupList.innerHTML = data.groups.map(g => `
            <div class="group-sidebar-item" onclick="openGroupPanel('${g.id}')">
                <span class="group-sidebar-name">${g.name}</span>
                <span class="group-sidebar-count">${(g.item_ids || []).length}개</span>
                <button class="group-delete-btn" onclick="event.stopPropagation();deleteGroup('${g.id}')" title="그룹 삭제">✕</button>
            </div>
        `).join('')
    } catch (e) {
        console.error('그룹 로드 실패:', e)
    }
}

// ── 그룹 상세 패널 열기 ──
async function openGroupPanel(groupId) {
    openRightPanel('그룹', '<div class="chat-loading">···</div>')
    try {
        const data = await fetch(`/api/groups/${groupId}/items`).then(r => r.json())
        panelTitle.textContent = data.group.name
        if (!data.items.length) {
            panelBody.innerHTML = '<p class="no-result">이 그룹에 자료가 없어요.</p>'
            return
        }
        panelBody.innerHTML = data.items.map(item => {
            const thumbHTML = item.thumbnail
                ? `<img src="${item.thumbnail}" style="width:100%;height:130px;object-fit:cover;border-radius:8px;margin-bottom:10px;display:block" onerror="this.style.display='none'" alt="" />`
                : ''
            return `
                <div class="panel-item-card" id="card-${item.id}">
                    ${thumbHTML}
                    <p class="panel-item-title">${item.title}</p>
                    ${item.summary ? `<p class="panel-item-summary">${item.summary}</p>` : ''}
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
                        <a href="${item.url}" target="_blank" class="panel-item-link">링크 열기 &rarr;</a>
                        <button class="delete-item-btn" onclick="deleteContent('${item.id}', this)" title="삭제">🗑</button>
                    </div>
                </div>
            `
        }).join('')
    } catch (e) {
        panelBody.innerHTML = `<p class="error-msg">${e.message}</p>`
    }
}

// ── 채팅 패널 열기 (접었다 폈다 — 히스토리 유지) ──
function openChatPanel(initialText = '') {
    chatPanelOpen = true

    // 기존 메시지 HTML 재빌드
    const existingMsgs = chatDomMsgs.map(m =>
        `<div class="chat-msg ${m.role}">${m.isHtml ? m.content : escHtml(m.content)}</div>`
    ).join('')
    const greet = chatDomMsgs.length === 0
        ? '<div class="chat-msg ai">안녕하세요! URL을 붙여넣으면 저장하고, 그 외 메시지는 AI와 대화할 수 있어요.</div>'
        : ''

    openRightPanel('AI 어시스턴트', `
        <div class="chat-container">
            <div class="chat-messages" id="chat-messages">
                ${greet}${existingMsgs}
            </div>
            <div class="chat-input-wrap">
                <input type="text" id="chat-input" class="chat-input" placeholder="URL 붙여넣기 또는 메시지 입력" />
                <button id="chat-send" class="chat-send-btn">&#8594;</button>
            </div>
        </div>
    `, true)

    const chatInput = document.getElementById('chat-input')
    const chatSend  = document.getElementById('chat-send')
    chatSend.addEventListener('click', sendChat)
    chatInput.addEventListener('keydown', e => { if (e.key === 'Enter') sendChat() })
    chatInput.focus()

    // 스크롤 맨 아래
    const msgs = document.getElementById('chat-messages')
    if (msgs) msgs.scrollTop = msgs.scrollHeight

    if (initialText) {
        chatInput.value = initialText
        setTimeout(sendChat, 60)
    }
}

function escHtml(str) {
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

// ── 채팅 메시지 전송 (URL 붙여넣기 → 저장 / 텍스트 → AI 대화) ──
async function sendChat() {
    const chatInput    = document.getElementById('chat-input')
    const chatSend     = document.getElementById('chat-send')
    const chatMessages = document.getElementById('chat-messages')
    if (!chatInput) return

    const text = chatInput.value.trim()
    if (!text) return

    // 사용자 메시지 DOM + 히스토리 기록
    appendMsg(chatMessages, 'user', text)
    chatDomMsgs.push({ role: 'user', content: text, isHtml: false })
    chatHistory.push({ role: 'user', content: text })
    chatInput.value = ''
    chatSend.disabled = true

    const loadingEl = document.createElement('div')
    loadingEl.className = 'chat-loading'
    loadingEl.textContent = '···'
    chatMessages.appendChild(loadingEl)
    chatMessages.scrollTop = chatMessages.scrollHeight

    try {
        // 텍스트에서 URL 모두 추출
        const urlMatches = text.match(/https?:\/\/[^\s]+/g) || []
        const firstWordUrl = isURL(text.split(' ')[0])

        if (firstWordUrl && urlMatches.length > 0) {
            // URL 저장 — 여러 개면 순차 처리
            loadingEl.remove()
            for (const url of urlMatches) {
                const saveLoading = document.createElement('div')
                saveLoading.className = 'chat-loading'
                saveLoading.textContent = '···'
                chatMessages.appendChild(saveLoading)

                const res  = await fetch('/api/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                })
                const data = await res.json()
                saveLoading.remove()

                if (!res.ok || data.error) {
                    appendMsg(chatMessages, 'ai', `오류: ${data.error || '저장 실패'}`)
                    chatDomMsgs.push({ role: 'assistant', content: `오류: ${data.error || '저장 실패'}`, isHtml: false })
                } else {
                    const aiEl = document.createElement('div')
                    aiEl.className = 'chat-msg ai'
                    const html = buildSavedItemContent(data.item)
                    aiEl.innerHTML = html
                    chatMessages.appendChild(aiEl)
                    chatDomMsgs.push({ role: 'assistant', content: html, isHtml: true })
                    chatHistory.push({ role: 'assistant', content: `'${data.item?.title || url}' 저장 완료` })
                }
                chatMessages.scrollTop = chatMessages.scrollHeight
            }
            loadTopFolders()
        } else {
            // 텍스트 → AI 대화 (히스토리 포함)
            const res  = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    history: chatHistory.slice(-20),
                    context: activeContext,   // 현재 활성 컨텍스트 전달
                })
            })
            const data = await res.json()
            loadingEl.remove()

            const aiEl = document.createElement('div')
            aiEl.className = 'chat-msg ai'
            const html = buildAIContent(data)
            aiEl.innerHTML = html
            chatMessages.appendChild(aiEl)

            // 어시스턴트 응답 히스토리 기록
            const answerText = data.message || data.answer || ''
            chatDomMsgs.push({ role: 'assistant', content: html, isHtml: true })
            chatHistory.push({ role: 'assistant', content: answerText })

            if (data.type === 'create_group' && data.group) {
                // activeContext에 그룹 정보 저장 → 이후 "이 그룹 요약해줘" 등에서 활용
                activeContext = {
                    type:  'group',
                    group: { id: data.group.id, name: data.group.name },
                    items: (data.items || []).map(i => ({ id: i.id, title: i.title, summary: i.summary || i.one_line_summary || '' })),
                }
                // 히스토리에도 context 주입 (LLM이 다음 턴에 기억)
                chatHistory.push({
                    role: 'system',
                    content: `현재 활성 그룹: "${data.group.name}"\n포함 콘텐츠:\n${activeContext.items.map((it, i) => `${i+1}. ${it.title}`).join('\n')}`,
                })
                await loadGroups()
            }

            // 검색 결과가 있으면 activeContext 업데이트
            if (data.items && data.items.length && data.intent === 'search') {
                activeContext = {
                    type:  'search',
                    group: null,
                    items: data.items.map(i => ({ id: i.id, title: i.title, summary: i.summary || i.one_line_summary || '' })),
                }
            }
        }
    } catch (e) {
        loadingEl.remove()
        appendMsg(chatMessages, 'ai', `오류: ${e.message}`)
        chatDomMsgs.push({ role: 'assistant', content: `오류: ${e.message}`, isHtml: false })
    } finally {
        chatSend.disabled = false
        chatMessages.scrollTop = chatMessages.scrollHeight
    }
}

// URL 저장 결과를 채팅 버블로 표시 (썸네일 포함)
function buildSavedItemContent(item) {
    const tags = Array.isArray(item.tags) ? item.tags : (item.tags ? JSON.parse(item.tags) : [])
    const thumbHTML = item.thumbnail
        ? `<img src="${item.thumbnail}" style="width:100%;height:140px;object-fit:cover;border-radius:8px;margin-bottom:10px;display:block" onerror="this.style.display='none'" alt="" />`
        : ''
    return `
        <div style="font-size:11px;font-weight:700;color:#5A9A60;margin-bottom:8px;letter-spacing:0.3px">✓ 저장 완료</div>
        ${thumbHTML}
        <div style="font-size:14px;font-weight:600;color:#2C1A0E;margin-bottom:4px;line-height:1.4">${item.title}</div>
        <div style="font-size:12px;color:#9A7055;margin-bottom:8px">${item.category} / ${item.subcategory}</div>
        ${item.summary ? `<div style="font-size:13px;color:#6B4E3A;line-height:1.55;margin-bottom:8px">${item.summary}</div>` : ''}
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

// 아이템 카드 뉴스 HTML (썸네일 포함)
function buildResultCards(items, maxCount = 5) {
    const preview  = items.slice(0, maxCount)
    const more     = items.length - maxCount
    const cardsHTML = preview.map(item => {
        const thumbHTML = item.thumbnail
            ? `<img src="${item.thumbnail}" class="msg-card-thumb" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" alt="" /><div class="msg-card-thumb-placeholder" style="display:none">📄</div>`
            : `<div class="msg-card-thumb-placeholder">📄</div>`
        return `
            <a href="${item.url}" target="_blank" class="msg-result-card">
                ${thumbHTML}
                <div class="msg-card-body">
                    <div class="msg-card-category">${item.category || ''} ${item.subcategory ? '/ ' + item.subcategory : ''}</div>
                    <div class="msg-card-title">${item.title}</div>
                    ${item.summary ? `<div class="msg-card-summary">${item.summary}</div>` : ''}
                    <span class="msg-card-link">링크 열기 →</span>
                </div>
            </a>
        `
    }).join('')
    return `<div class="msg-result-cards">${cardsHTML}${more > 0 ? `<span class="msg-more">외 ${more}개</span>` : ''}</div>`
}

// AI 응답 HTML 빌드 (그룹카드 / 검색결과 포함)
function buildAIContent(data) {
    let html = data.message || ''

    if (data.items && data.items.length) {
        if (data.type === 'create_group' && data.group) {
            const key = ++editStoreSeq
            editStore[key] = { id: data.group.id, name: data.group.name, items: data.items }
            html += `
                <div class="msg-group-card">
                    <div class="msg-group-title">
                        ${data.group.name}
                        <button class="msg-edit-btn" onclick="openGroupEdit(${key})">수정하기</button>
                    </div>
                    ${buildResultCards(data.items)}
                </div>
            `
        } else {
            html += buildResultCards(data.items)
        }
    }
    return html
}

// ── 그룹 수정 모달 ──
function openGroupEdit(storeKey) {
    const d = editStore[storeKey]
    if (!d) return
    editGroupId    = d.id
    editGroupItems = [...d.items]
    document.getElementById('group-edit-name').value = d.name
    renderEditItems()
    groupEditModal.classList.add('open')
}

function renderEditItems() {
    document.getElementById('group-edit-items').innerHTML = editGroupItems.map((item, i) => `
        <div class="edit-item-row">
            <span class="edit-item-title">${item.title}</span>
            <button class="edit-item-remove" onclick="removeEditItem(${i})">&#x2715;</button>
        </div>
    `).join('')
}

window.removeEditItem = function(i) {
    editGroupItems.splice(i, 1)
    renderEditItems()
}

document.getElementById('group-edit-close').addEventListener('click', () => {
    groupEditModal.classList.remove('open')
})

document.getElementById('group-edit-save').addEventListener('click', async () => {
    const name = document.getElementById('group-edit-name').value.trim()
    if (!name || editGroupId === null) return
    await fetch(`/api/groups/${editGroupId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, item_ids: editGroupItems.map(i => i.id) })
    })
    groupEditModal.classList.remove('open')
    await loadGroups()
})

groupEditModal.addEventListener('click', e => {
    if (e.target === groupEditModal) groupEditModal.classList.remove('open')
})

// ── 그룹 삭제 ──
window.deleteGroup = async function(groupId) {
    if (!confirm('이 그룹을 삭제할까요?')) return
    const res = await fetch(`/api/groups/${groupId}`, { method: 'DELETE' })
    if (res.ok) {
        await loadGroups()
    } else {
        alert('그룹 삭제에 실패했어요.')
    }
}

// ── 콘텐츠 삭제 ──
window.deleteContent = async function(contentId, cardEl) {
    if (!confirm('이 콘텐츠를 삭제할까요?')) return
    const res = await fetch(`/api/contents/${contentId}`, { method: 'DELETE' })
    if (res.ok) {
        cardEl?.closest('.archive-item-card, .panel-item-card')?.remove()
    } else {
        alert('삭제에 실패했어요.')
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
            const date = item.created_at ? item.created_at.slice(0, 10) : ''
            return `
                <div class="archive-item-card" id="card-${item.id}">
                    ${item.content_type !== 'music' && item.summary ? `<p class="archive-item-summary">${item.summary}</p>` : ''}
                    <p class="archive-item-title">${item.title}</p>
                    ${tags.length ? `<div class="archive-item-tags">${tags.map(t => `<span class="tag">#${t}</span>`).join('')}</div>` : ''}
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">
                        <span class="archive-item-meta">${date}</span>
                        <div style="display:flex;gap:8px;align-items:center">
                            <a href="${item.url}" target="_blank" class="archive-item-link">링크 열기 &rarr;</a>
                            <button class="delete-item-btn" onclick="deleteContent('${item.id}', this)" title="삭제">🗑</button>
                        </div>
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
    const data = await fetch('/api/reminders').then(r => r.json())
    if (!data.length) {
        openModal('리마인더', '<p class="no-result">3일 이내 마감 자료가 없어요.</p>')
        return
    }
    openModal('리마인더', data.map(r => `
        <div class="reminder-item">
            <span class="reminder-deadline">마감: ${r.deadline}</span>
            <p class="reminder-title">${r.title}</p>
            <span class="reminder-cat">${r.category}</span>
            <a href="${r.url}" target="_blank" class="card-link">링크 열기 &rarr;</a>
        </div>
    `).join(''))
})

document.getElementById('btn-report').addEventListener('click', async () => {
    const data = await fetch('/api/monthly-report').then(r => r.json())
    const statsHtml = data.stats.map(s => `
        <div class="stat-row">
            <span>${s.category} / ${s.subcategory}</span>
            <span class="stat-count">${s.count}개</span>
        </div>
    `).join('')
    openModal('월간 취향 레포트', `
        <div class="report-text">${data.report}</div>
        ${statsHtml ? `<div class="stats-list">${statsHtml}</div>` : ''}
    `)
})

// 주간 레포트 — 전용 페이지로 이동
document.getElementById('btn-weekly-report').addEventListener('click', () => {
    window.location.href = '/weekly-report'
})

// ── 초기 로드 ──
loadTopFolders()
loadGroups()

// URL 저장 시 채팅 버블 표시, 자연어 입력 시 AI 채팅 패널 오픈 / 폴더 클릭 시 카테고리 상세 패널 표시 / 그룹 생성 시 좌측 사이드바 업데이트
