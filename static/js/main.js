// ── Keepit 메인 인터랙션 ──

// 로그인한 사용자 id (index.html에서 주입). 없으면 기본 계정으로 폴백
const DEFAULT_USER_ID = window.__USER_ID__ || '00000000-0000-0000-0000-000000000001'

// 채팅 세션 상태 (패널 열릴 때 초기화)
let chatHistory = []
let shownIds = new Set()
let lastSavedIds = []   // 방금 저장한 콘텐츠 id ("이 콘텐츠 요약" 직행용)

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

// 입력에서 모든 URL 추출
function extractUrls(text) {
    const re = /(https?:\/\/[^\s]+|www\.[^\s]+)/gi
    return (text.match(re) || []).map(u => u.replace(/[.,)\]]+$/, ''))
}

// 자연어에서 대상 컬렉션 이름 추출 ("○○ 컬렉션/폴더에 저장/담아/넣어")
function parseCollectionName(text) {
    const m = text.match(/([가-힣A-Za-z0-9][가-힣A-Za-z0-9 ]*?)\s*(?:컬렉션|폴더)\s*에?\s*(?:저장|넣어|넣|담아|담|추가|모아|올려)/)
    if (!m) return null
    let name = m[1].trim()
    name = name.replace(/^(를|을|은|는|이|가|에|에서|로|으로|와|과|도|만|,)\s*/, '').trim()
    return name || null
}

function showResults(html) {
    resultsDiv.innerHTML = html
    resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

function setLoading(on) {
    submitBtn.disabled = on
    submitBtn.innerHTML = on ? '&#8230;' : '&#8594;'
}

// ── 채팅 패널 (#right-panel — 채팅 전용) ──
function openRightPanel(title, content, fullscreen = false) {
    panelTitle.textContent = title
    panelBody.innerHTML = content
    rightPanel.classList.add('open')
    document.querySelector('.page-wrapper').classList.toggle('chat-fullscreen', fullscreen)
    const reopen = document.getElementById('panel-reopen')
    if (reopen) reopen.style.display = 'none'
}

// 채팅 접기 (내용은 유지 → '채팅 열기' 버튼으로 복원)
function closeRightPanel() {
    rightPanel.classList.remove('open')
    document.querySelector('.page-wrapper').classList.remove('chat-fullscreen')
    const reopen = document.getElementById('panel-reopen')
    if (reopen && panelBody.innerHTML.trim()) reopen.style.display = 'flex'
}

// '채팅 열기' — 어느 상황에서든 항상 채팅 화면을 연다
window.reopenPanel = function () {
    rightPanel.classList.add('open')
    document.querySelector('.page-wrapper').classList.add('chat-fullscreen')
    const reopen = document.getElementById('panel-reopen')
    if (reopen) reopen.style.display = 'none'
}

// ── 상세 패널 (#detail-panel — 컬렉션/카테고리, 채팅과 분리) ──
function openDetailPanel(title, content, headerActions = '') {
    document.getElementById('detail-title').textContent = title
    document.getElementById('detail-header-actions').innerHTML = headerActions
    document.getElementById('detail-body').innerHTML = content
    document.getElementById('detail-panel').classList.add('open')
    document.body.classList.add('detail-open')   // 채팅 열기 아이콘을 패널 옆으로 이동
}

window.closeDetailPanel = function () {
    document.getElementById('detail-panel').classList.remove('open')
    document.body.classList.remove('detail-open')
}

// ── 메인 '자주 보는 컬렉션' 설정 (localStorage) ──
function folderSettingKey() { return `keepit_pinned_${DEFAULT_USER_ID}` }

function getFolderSetting() {
    try { return JSON.parse(localStorage.getItem(folderSettingKey())) || { mode: 'auto', ids: [] } }
    catch (e) { return { mode: 'auto', ids: [] } }
}

function setFolderSetting(s) { localStorage.setItem(folderSettingKey(), JSON.stringify(s)) }

// ── 컬렉션 클릭 횟수 추적 (자동 정렬용) ──
function clickKey() { return `keepit_clicks_${DEFAULT_USER_ID}` }

function getClicks() {
    try { return JSON.parse(localStorage.getItem(clickKey())) || {} }
    catch (e) { return {} }
}

function bumpCollectionClick(id) {
    const m = getClicks()
    m[id] = (m[id] || 0) + 1
    localStorage.setItem(clickKey(), JSON.stringify(m))
}

// 폴더 카드 1개 HTML
function folderCardHTML(c) {
    return `
        <div class="folder-card" onclick="openCollectionPanel('${esc(c.id)}','${esc(c.name)}')">
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
                <span class="folder-name">${c.name}</span>
                <span class="folder-count">${c.content_count || 0}개</span>
            </div>
        </div>
    `
}

// ── 메인: 자주 보는 컬렉션 5개 로드 ──
async function loadTopFolders() {
    try {
        const data = await fetch(`/collections/${DEFAULT_USER_ID}`).then(r => r.json())
        const collections = data.collections || []
        const folderGrid = document.getElementById('folder-grid')

        const editBtn0 = document.getElementById('edit-folders-btn')
        if (!collections.length) {
            folderGrid.innerHTML = '<div class="folder-placeholder">아직 컬렉션이 없어요</div>'
            if (editBtn0) editBtn0.style.display = 'none'
            return
        }

        const setting = getFolderSetting()
        let pinned
        if (setting.mode === 'custom' && setting.ids.length) {
            const byId = Object.fromEntries(collections.map(c => [c.id, c]))
            pinned = setting.ids.map(id => byId[id]).filter(Boolean).slice(0, 5)
        } else {
            // 자동: 클릭 많은 순 5개 (동률이면 콘텐츠 수 순)
            const clicks = getClicks()
            pinned = [...collections].sort((a, b) => {
                const diff = (clicks[b.id] || 0) - (clicks[a.id] || 0)
                return diff !== 0 ? diff : (b.content_count || 0) - (a.content_count || 0)
            }).slice(0, 5)
        }

        folderGrid.innerHTML = pinned.length
            ? pinned.map(folderCardHTML).join('')
            : '<div class="folder-placeholder">표시할 컬렉션이 없어요</div>'

        // 편집(연필) 아이콘은 컬렉션이 있을 때만 노출
        const editBtn = document.getElementById('edit-folders-btn')
        if (editBtn) editBtn.style.display = collections.length ? 'inline-flex' : 'none'
    } catch (e) {
        console.error('폴더 로드 실패:', e)
    }
}

// ── 자주 보는 컬렉션 편집 (우측 슬라이드 사이드바, X로 닫기) ──
async function openFolderSettings() {
    const data = await fetch(`/collections/${DEFAULT_USER_ID}`).then(r => r.json())
    const collections = data.collections || []
    if (!collections.length) return

    const setting = getFolderSetting()
    document.getElementById('folder-edit-panel')?.remove()

    const checks = collections.map(c => `
        <label class="pin-item">
            <input type="checkbox" class="pin-check" value="${esc(c.id)}" ${setting.mode === 'custom' && setting.ids.includes(c.id) ? 'checked' : ''} />
            <span class="pin-name">${c.name}</span>
            <span class="pin-count">${c.content_count || 0}개</span>
        </label>
    `).join('')

    const panel = document.createElement('div')
    panel.id = 'folder-edit-panel'
    panel.className = 'folder-edit-panel'
    panel.innerHTML = `
        <div class="fe-header">
            <span class="fe-title">메인 노출 컬렉션 편집</span>
            <button class="fe-close" onclick="closeFolderSettings()" aria-label="닫기">&times;</button>
        </div>
        <div class="fe-body">
            <label class="fe-label">표시 방식</label>
            <div class="fe-dropdown" id="fe-dropdown">
                <button type="button" class="fe-dd-toggle" onclick="toggleFeDropdown()">
                    <span id="fe-dd-label">${setting.mode === 'custom' ? '사용자 설정' : '자주 사용하는 컬렉션'}</span>
                    <svg class="fe-dd-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                </button>
                <div class="fe-dd-menu">
                    <button type="button" class="fe-dd-item" onclick="selectFeMode('auto','자주 사용하는 컬렉션')">자주 사용하는 컬렉션</button>
                    <button type="button" class="fe-dd-item" onclick="selectFeMode('custom','사용자 설정')">사용자 설정</button>
                </div>
            </div>
            <input type="hidden" id="fe-mode" value="${setting.mode === 'custom' ? 'custom' : 'auto'}" />
            <div id="fe-list" class="pin-list">${checks}</div>
            <button class="summarize-go-btn" onclick="saveFolderSettings()">저장</button>
        </div>
    `
    document.body.appendChild(panel)
    requestAnimationFrame(() => panel.classList.add('open'))
    feToggleList()
}

// 커스텀 드롭다운 토글/선택
window.toggleFeDropdown = function () {
    document.getElementById('fe-dropdown')?.classList.toggle('open')
}

window.selectFeMode = function (mode, label) {
    const hidden = document.getElementById('fe-mode')
    if (hidden) hidden.value = mode
    const lbl = document.getElementById('fe-dd-label')
    if (lbl) lbl.textContent = label
    document.getElementById('fe-dropdown')?.classList.remove('open')
    feToggleList()
}

window.closeFolderSettings = function () {
    const p = document.getElementById('folder-edit-panel')
    if (!p) return
    p.classList.remove('open')
    setTimeout(() => p.remove(), 250)
}

// 드롭다운 모드에 따라 체크리스트 활성/비활성
window.feToggleList = function () {
    const mode = document.getElementById('fe-mode')?.value
    const list = document.getElementById('fe-list')
    if (!list) return
    const on = mode === 'custom'
    list.style.opacity = on ? '1' : '0.4'
    list.style.pointerEvents = on ? 'auto' : 'none'
}

// 설정 저장 → 메인 갱신
window.saveFolderSettings = function () {
    const mode = document.getElementById('fe-mode')?.value || 'auto'
    let ids = []
    if (mode === 'custom') {
        ids = [...document.querySelectorAll('#fe-list .pin-check:checked')].map(c => c.value)
        if (!ids.length) { alert('컬렉션을 1개 이상 선택해주세요.'); return }
        if (ids.length > 5) { alert('최대 5개까지 선택할 수 있어요.'); return }
    }
    setFolderSetting({ mode, ids })
    closeFolderSettings()
    loadTopFolders()
}

// ── 카테고리 패널 열기 (상세 패널 사용) ──
async function openCategoryPanel(category, subcategory) {
    openDetailPanel(`${category} / ${subcategory}`, '<div class="chat-loading">···</div>')
    const body = document.getElementById('detail-body')
    try {
        const params = new URLSearchParams({ category, subcategory, user_id: DEFAULT_USER_ID })
        const data = await fetch(`/api/items?${params}`).then(r => r.json())
        if (!data.items.length) {
            body.innerHTML = '<p class="no-result">저장된 자료가 없어요.</p>'
            return
        }
        body.innerHTML = data.items.map(item => {
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
        body.innerHTML = `<p class="error-msg">${e.message}</p>`
    }
}

// ── 사이드바 접힘 상태 (localStorage) ──
function sidebarKey() { return `keepit_sb_${DEFAULT_USER_ID}` }
function isSidebarCollapsed() { return localStorage.getItem(sidebarKey()) === '1' }
function setSidebarCollapsed(v) { localStorage.setItem(sidebarKey(), v ? '1' : '0') }

function applySidebarState(hasCollections) {
    const sidebar = document.getElementById('left-sidebar')
    sidebar.classList.remove('open', 'collapsed')
    if (!hasCollections) return
    // 접힘이면 '내 컬렉션' 탭만 남기고, 펼침이면 전체 노출
    sidebar.classList.add(isSidebarCollapsed() ? 'collapsed' : 'open')
}

window.toggleSidebar = function () {
    const collapsed = !isSidebarCollapsed()
    setSidebarCollapsed(collapsed)
    const sidebar = document.getElementById('left-sidebar')
    sidebar.classList.toggle('open', !collapsed)
    sidebar.classList.toggle('collapsed', collapsed)
}

// ── 컬렉션(폴더) 사이드바 로드 ──
async function loadCollections() {
    try {
        const data = await fetch(`/collections/${DEFAULT_USER_ID}`).then(r => r.json())
        const list = document.getElementById('group-list')
        const cols = data.collections || []

        if (!cols.length) {
            applySidebarState(false)
            return
        }
        // 이름은 아이콘/이모지 없이 텍스트만 노출
        list.innerHTML = cols.map(c => `
            <button class="group-sidebar-item" onclick="openCollectionPanel('${esc(c.id)}','${esc(c.name)}')">
                <span class="group-sidebar-name">${c.name}</span>
                ${c.content_count ? `<span class="group-sidebar-count">${c.content_count}</span>` : ''}
            </button>
        `).join('')
        applySidebarState(true)
    } catch (e) {
        console.error('컬렉션 로드 실패:', e)
    }
}

const PENCIL_SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>'
const SAVE_SVG   = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
const TRASH_SVG  = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>'

// ── 컬렉션 상세 패널 열기 (제목 옆 수정·삭제 아이콘 / 콘텐츠 추가·선택·전체삭제) ──
async function openCollectionPanel(collectionId, name) {
    bumpCollectionClick(collectionId)   // 클릭 횟수 누적 → 메인 자동 정렬에 반영
    const headerActions = `
        <button class="detail-icon-btn" id="coll-edit-btn" title="이름 수정" onclick="startRenameCollection('${esc(collectionId)}')">${PENCIL_SVG}</button>
        <button class="detail-icon-btn danger" title="폴더 삭제" onclick="deleteCollection('${esc(collectionId)}','${esc(name)}')">${TRASH_SVG}</button>
    `
    openDetailPanel(name, '<div class="chat-loading">···</div>', headerActions)
    try {
        const data = await fetch(`/api/collections/${collectionId}/items?user_id=${DEFAULT_USER_ID}`).then(r => r.json())
        const body = document.getElementById('detail-body')

        const toolbar = `
            <div class="collection-toolbar">
                <button class="manage-btn" onclick="openAddToCollection('${esc(collectionId)}','${esc(name)}')">+ 콘텐츠 추가</button>
                <button class="manage-btn" onclick="deleteSelectedCollection('${esc(collectionId)}','${esc(name)}')">선택 삭제</button>
                <button class="manage-btn" onclick="deleteAllCollection('${esc(collectionId)}','${esc(name)}')">전체 삭제</button>
            </div>
        `

        if (!data.items.length) {
            body.innerHTML = toolbar + '<p class="no-result">이 폴더에 자료가 없어요.</p>'
            return
        }
        body.innerHTML = toolbar + data.items.map(item => {
            const tags = Array.isArray(item.tags) ? item.tags : []
            const thumbHTML = item.thumbnail
                ? `<img src="${item.thumbnail}" style="width:100%;height:130px;object-fit:cover;border-radius:8px;margin-bottom:10px;display:block" onerror="this.style.display='none'" alt="" />`
                : ''
            return `
                <div class="panel-item-card">
                    <button class="item-x-btn" title="이 폴더에서 빼기" onclick="removeFromCollection('${esc(collectionId)}','${esc(item.id)}','${esc(name)}')">&times;</button>
                    <label class="arch-select">
                        <input type="checkbox" class="coll-check" value="${esc(item.id)}" />
                        <span>선택</span>
                    </label>
                    ${thumbHTML}
                    <p class="panel-item-title">${item.title}</p>
                    ${item.summary ? `<p class="panel-item-summary">${item.summary}</p>` : ''}
                    ${tags.length ? `<div class="card-tags" style="margin-bottom:8px">${tags.map(t => `<span class="tag">#${t}</span>`).join('')}</div>` : ''}
                    <div class="panel-item-actions">
                        <a href="${item.url}" target="_blank" class="panel-item-link">링크 열기 &rarr;</a>
                    </div>
                </div>
            `
        }).join('')
    } catch (e) {
        document.getElementById('detail-body').innerHTML = `<p class="error-msg">${e.message}</p>`
    }
}

// 제목 옆 수정 아이콘 클릭 → 제목 입력 활성화 + 아이콘이 저장으로 변경
window.startRenameCollection = function (collectionId) {
    const titleEl = document.getElementById('detail-title')
    const cur = titleEl.textContent
    titleEl.innerHTML = `<input id="coll-name-input" class="detail-title-input" value="${cur.replace(/"/g, '&quot;')}" />`
    const btn = document.getElementById('coll-edit-btn')
    btn.title = '저장'
    btn.innerHTML = SAVE_SVG
    btn.setAttribute('onclick', `saveRenameCollection('${esc(collectionId)}')`)
    const input = document.getElementById('coll-name-input')
    input.focus()
    input.addEventListener('keydown', e => { if (e.key === 'Enter') saveRenameCollection(collectionId) })
}

// 저장 아이콘 클릭 → 수정한 제목 저장
window.saveRenameCollection = async function (collectionId) {
    const input = document.getElementById('coll-name-input')
    const name = (input?.value || '').trim()
    if (!name) return
    try {
        const res = await fetch(`/collections/${collectionId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: DEFAULT_USER_ID, name }),
        })
        if (!res.ok) throw new Error('이름 변경 실패')
        loadCollections()
        loadTopFolders()
        openCollectionPanel(collectionId, name)   // 새 이름으로 패널 갱신
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
        closeDetailPanel()
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

// ── 컬렉션에 콘텐츠 추가 (현재 폴더에 없는 콘텐츠 선택) ──
window.openAddToCollection = async function (collectionId, name) {
    try {
        const [all, current] = await Promise.all([
            fetch(`/api/items?user_id=${DEFAULT_USER_ID}`).then(r => r.json()),
            fetch(`/api/collections/${collectionId}/items?user_id=${DEFAULT_USER_ID}`).then(r => r.json()),
        ])
        const inIds = new Set((current.items || []).map(i => i.id))
        const candidates = (all.items || []).filter(i => !inIds.has(i.id))
        if (!candidates.length) {
            openModal('콘텐츠 추가', '<p class="no-result">추가할 콘텐츠가 없어요.</p>')
            return
        }
        const list = candidates.map(i => `
            <label class="pin-item">
                <input type="checkbox" class="add-check" value="${esc(i.id)}" />
                <span class="pin-name">${i.title || '제목 없음'}</span>
            </label>
        `).join('')
        openModal(`'${name}'에 콘텐츠 추가`, `
            <div class="pin-list">${list}</div>
            <button class="summarize-go-btn" onclick="confirmAddToCollection('${esc(collectionId)}','${esc(name)}')">선택 추가</button>
        `)
    } catch (e) {
        alert('목록을 불러오지 못했어요: ' + e.message)
    }
}

window.confirmAddToCollection = async function (collectionId, name) {
    const ids = [...document.querySelectorAll('.add-check:checked')].map(c => c.value)
    if (!ids.length) { alert('추가할 콘텐츠를 선택해주세요.'); return }
    try {
        const res = await fetch('/contents/move', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: DEFAULT_USER_ID, content_ids: ids, target_folder: name }),
        })
        if (!res.ok) throw new Error('추가 실패')
        closeModal()
        openCollectionPanel(collectionId, name)
        loadTopFolders()
        loadCollections()
    } catch (e) {
        alert('추가 실패: ' + e.message)
    }
}

// ── 폴더 패널: 선택한 콘텐츠 복수 영구 삭제 ──
window.deleteSelectedCollection = async function (collectionId, name) {
    const ids = [...document.querySelectorAll('.coll-check:checked')].map(c => c.value)
    if (!ids.length) { alert('삭제할 콘텐츠를 선택해주세요.'); return }
    if (!confirm(`선택한 ${ids.length}개 콘텐츠를 영구 삭제할까요?\n되돌릴 수 없습니다.`)) return
    await _bulkDeleteContents(ids)
    openCollectionPanel(collectionId, name)
    loadTopFolders()
    loadCollections()
}

// ── 폴더 패널: 폴더 안 콘텐츠 전체 영구 삭제 ──
window.deleteAllCollection = async function (collectionId, name) {
    const ids = [...document.querySelectorAll('.coll-check')].map(c => c.value)
    if (!ids.length) { alert('삭제할 콘텐츠가 없어요.'); return }
    if (!confirm(`이 폴더의 ${ids.length}개 콘텐츠를 모두 영구 삭제할까요?\n(폴더는 남고 콘텐츠만 삭제됩니다)\n되돌릴 수 없습니다.`)) return
    await _bulkDeleteContents(ids)
    openCollectionPanel(collectionId, name)
    loadTopFolders()
    loadCollections()
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

    try {
        const urls = extractUrls(text)
        if (urls.length) {
            // URL(들) → 저장. 자연어 요청(컬렉션 지정·마감)도 함께 해석
            lastSavedIds = []   // 새 저장 배치 시작 → "이 콘텐츠" 기준 초기화
            const deadlineMatch = text.match(/마감[：:]\s*(\d{4}-\d{2}-\d{2})/)
            const deadline = deadlineMatch ? deadlineMatch[1] : null
            let nl = text
            urls.forEach(u => { nl = nl.replace(u, ' ') })
            nl = nl.replace(/마감[：:]\s*\d{4}-\d{2}-\d{2}/, '').trim()
            const collectionName = parseCollectionName(nl)
            let instruction = nl
            if (deadline) instruction = `${instruction} 마감기한: ${deadline}`.trim()

            let saved = 0
            for (let idx = 0; idx < urls.length; idx++) {
                const url = urls[idx]
                const pos = urls.length > 1 ? `(${idx + 1}/${urls.length}) ` : ''
                showChatStatus([`${pos}링크 저장 중`, `${pos}콘텐츠 분석 중`])
                try {
                    const res = await fetch('/ingest', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url, user_id: DEFAULT_USER_ID, instruction, collection_name: collectionName })
                    })
                    const data = await res.json()
                    hideChatStatus()
                    if (!res.ok || data.error) { appendMsg(chatMessages, 'ai', `저장 실패: ${url}`); continue }

                    const aiEl = document.createElement('div')
                    aiEl.className = 'chat-msg ai'
                    aiEl.innerHTML = data.duplicate ? buildSavedItemContent(data.content, true) : buildSavedItemContent(data)
                    chatMessages.appendChild(aiEl)
                    if (data.reminder_message) appendMsg(chatMessages, 'ai', data.reminder_message)
                    // 방금 저장한 콘텐츠 id 수집 ("이 콘텐츠 요약" 직행용)
                    const savedId = data.duplicate ? (data.content && data.content.id) : data.id
                    if (savedId) lastSavedIds.push(savedId)
                    saved++
                } catch (err) {
                    appendMsg(chatMessages, 'ai', `저장 실패: ${url}`)
                }
                chatMessages.scrollTop = chatMessages.scrollHeight
            }
            hideChatStatus()
            if (urls.length > 1 || collectionName) {
                const where = collectionName ? ` '${collectionName}' 컬렉션에 담았어요.` : '.'
                appendMsg(chatMessages, 'ai', `링크 ${saved}개를 저장했어요${where}`)
            }
            loadTopFolders()
            loadCollections()
        } else {
            // 텍스트 → AI 대화 (실제 단계별 멘트가 뜨는 SSE 스트리밍, 실패 시 /chat 폴백)
            showChatStatus('요청 보내는 중')
            chatHistory.push({ role: 'user', content: text })
            const body = JSON.stringify({
                query: text,
                user_id: DEFAULT_USER_ID,
                history: chatHistory.slice(-10),
                shown_ids: [...shownIds],
                recent_saved_ids: lastSavedIds,
            })
            const data = await chatViaStream(body)

            hideChatStatus()
            if (!data) {
                appendMsg(chatMessages, 'ai', '오류가 발생했어요. 다시 시도해주세요.')
            } else {
                if (data.results) data.results.forEach(r => r.id && shownIds.add(r.id))
                chatHistory.push({ role: 'assistant', content: data.answer || '' })
                const aiEl = document.createElement('div')
                aiEl.className = 'chat-msg ai'
                aiEl.innerHTML = buildAIContent(data)
                chatMessages.appendChild(aiEl)
                loadCollections()
            }
        }
    } catch (e) {
        hideChatStatus()
        appendMsg(chatMessages, 'ai', `오류: ${e.message}`)
    } finally {
        chatSend.disabled = false
        chatMessages.scrollTop = chatMessages.scrollHeight
    }
}

// SSE 스트리밍으로 /chat 처리 — 단계 멘트를 실시간 갱신, 최종 result 반환. 실패 시 /chat 폴백
async function chatViaStream(body) {
    try {
        const res = await fetch('/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body,
        })
        if (!res.ok || !res.body) throw new Error('stream unavailable')

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        let result = null
        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buf += decoder.decode(value, { stream: true })
            const parts = buf.split('\n\n')
            buf = parts.pop()
            for (const part of parts) {
                const dataLine = part.split('\n').find(l => l.startsWith('data:'))
                if (!dataLine) continue
                let evt
                try { evt = JSON.parse(dataLine.slice(5).trim()) } catch (_) { continue }
                if (evt.type === 'status') showChatStatus(evt.message)
                else if (evt.type === 'result') result = evt.data
                else if (evt.type === 'error') throw new Error(evt.message)
            }
        }
        if (result) return result
        throw new Error('no result')
    } catch (e) {
        // 스트리밍 미지원/실패 → 일반 /chat 폴백
        try {
            const res2 = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body,
            })
            return await res2.json()
        } catch (e2) {
            return null
        }
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

// ── 작동 로딩 상태 (사용자 말풍선 아래, 멘트만 흐르는 그라데이션) ──
let chatStatusTimer = null
function showChatStatus(messages) {
    const container = document.getElementById('chat-messages')
    if (!container) return
    const list = Array.isArray(messages) ? messages : [messages]
    clearInterval(chatStatusTimer); chatStatusTimer = null
    // 기존 멘트 요소가 있으면 텍스트만 갱신 (스트리밍 단계 전환이 부드럽게)
    let el = document.getElementById('chat-loading-ment')
    if (!el) {
        el = document.createElement('div')
        el.className = 'chat-loading-ment'
        el.id = 'chat-loading-ment'
        container.appendChild(el)
    }
    el.textContent = list[0]
    container.scrollTop = container.scrollHeight
    if (list.length > 1) {
        let i = 0
        chatStatusTimer = setInterval(() => {
            i = (i + 1) % list.length
            const cur = document.getElementById('chat-loading-ment')
            if (cur) cur.textContent = list[i]
        }, 1600)
    }
}
function hideChatStatus() {
    clearInterval(chatStatusTimer); chatStatusTimer = null
    document.getElementById('chat-loading-ment')?.remove()
}

// 검색 결과 카드 HTML
function buildResultCards(items, maxCount = 5) {
    const preview = items.slice(0, maxCount)
    const more    = items.length - maxCount
    const cardsHTML = preview.map(item => {
        const summary = item.one_line_summary || item.summary || ''
        const thumbHTML = item.thumbnail
            ? `<img src="${item.thumbnail}" class="msg-card-thumb" onerror="this.outerHTML='<div class=\\'msg-card-thumb-placeholder\\'>📄</div>'" alt="" />`
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

// 요약 대상 후보 카드 (체크박스 복수 선택)
function buildSelectableCards(items) {
    const cards = items.map(item => {
        const thumb = item.thumbnail
            ? `<img src="${item.thumbnail}" class="sum-card-thumb" onerror="this.style.display='none'" alt="" />`
            : ''
        return `
            <label class="sum-card">
                <input type="checkbox" class="sum-check" value="${esc(item.id)}" />
                ${thumb}
                <div class="sum-card-body">
                    <div class="sum-card-title">${item.title || '제목 없음'}</div>
                    ${item.summary ? `<div class="sum-card-summary">${item.summary}</div>` : ''}
                </div>
            </label>
        `
    }).join('')
    return `<div class="sum-cards">${cards}</div>
        <div class="bundle-actions">
            <button class="summarize-go-btn" onclick="summarizeSelected(this)">선택한 콘텐츠 요약하기</button>
            <button class="bundle-all-btn" onclick="summarizeAll(this)">전체 콘텐츠 요약하기</button>
        </div>`
}

// 묶기 후보 카드 (체크박스 기본 선택) + 선택/전체 묶기
function buildBundleCards(items, folderName) {
    const cards = items.map(item => {
        const thumb = item.thumbnail
            ? `<img src="${item.thumbnail}" class="sum-card-thumb" onerror="this.style.display='none'" alt="" />`
            : ''
        return `
            <label class="sum-card">
                <input type="checkbox" class="bundle-check" value="${esc(item.id)}" checked />
                ${thumb}
                <div class="sum-card-body">
                    <div class="sum-card-title">${item.title || '제목 없음'}</div>
                    ${item.summary ? `<div class="sum-card-summary">${item.summary}</div>` : ''}
                </div>
            </label>
        `
    }).join('')
    return `<div class="sum-cards">${cards}</div>
        <div class="bundle-actions">
            <button class="summarize-go-btn" onclick="bundleContents(this,'${esc(folderName)}',false)">선택 묶기</button>
            <button class="bundle-all-btn" onclick="bundleContents(this,'${esc(folderName)}',true)">전체 묶기</button>
        </div>`
}

// 선택/전체 묶기 실행
window.bundleContents = async function (btn, folderName, all) {
    const bubble = btn.closest('.chat-msg')
    const checks = [...bubble.querySelectorAll('.bundle-check')]
    const ids = (all ? checks : checks.filter(c => c.checked)).map(c => c.value)
    if (!ids.length) { alert('묶을 콘텐츠를 선택해주세요.'); return }

    const chatMessages = document.getElementById('chat-messages')
    btn.disabled = true
    showChatStatus(['묶을 콘텐츠 정리 중', '컬렉션에 담는 중'])

    try {
        const res = await fetch('/collections/bundle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: DEFAULT_USER_ID, name: folderName, content_ids: ids }),
        })
        const data = await res.json()
        hideChatStatus()
        if (!res.ok) throw new Error('묶기 실패')
        const aiEl = document.createElement('div')
        aiEl.className = 'chat-msg ai'
        aiEl.innerHTML = buildAIContent({
            answer: `'${folderName}' 컬렉션이 완성되었어요! ${data.moved}개를 담았어요.`,
            action: 'folder_created',
            collection_id: data.collection_id,
            collection_name: folderName,
        })
        chatMessages.appendChild(aiEl)
        loadTopFolders()
        loadCollections()
    } catch (e) {
        hideChatStatus()
        appendMsg(chatMessages, 'ai', `오류: ${e.message}`)
    } finally {
        chatMessages.scrollTop = chatMessages.scrollHeight
    }
}

// 선택/전체 콘텐츠 요약 — 클릭한 버튼 멘트를 사용자 말풍선으로 띄우고 바로 진행
window.summarizeSelected = function (btn) {
    const bubble = btn.closest('.chat-msg')
    const ids = [...bubble.querySelectorAll('.sum-check:checked')].map(c => c.value)
    if (!ids.length) { alert('요약할 콘텐츠를 선택해주세요.'); return }
    runSummarize(ids, '선택한 콘텐츠 요약하기')
}

window.summarizeAll = function (btn) {
    const bubble = btn.closest('.chat-msg')
    const ids = [...bubble.querySelectorAll('.sum-check')].map(c => c.value)
    if (!ids.length) { alert('요약할 콘텐츠가 없어요.'); return }
    runSummarize(ids, '전체 콘텐츠 요약하기')
}

// 검색 결과 직접 액션 — 요약 / 폴더로 묶기
window.summarizeResults = function (btn) {
    const ids = (btn.closest('.bundle-actions')?.dataset.ids || '').split(',').filter(Boolean)
    if (!ids.length) { alert('요약할 콘텐츠가 없어요.'); return }
    runSummarize(ids, '이 결과 요약하기')
}

window.bundleResults = function (btn) {
    const ids = (btn.closest('.bundle-actions')?.dataset.ids || '').split(',').filter(Boolean)
    if (!ids.length) { alert('묶을 콘텐츠가 없어요.'); return }
    const name = prompt('어떤 컬렉션으로 묶을까요? 폴더 이름을 입력하세요.')
    if (!name || !name.trim()) return
    bundleResultIds(ids, name.trim())
}

async function bundleResultIds(ids, name) {
    const chatMessages = document.getElementById('chat-messages')
    appendMsg(chatMessages, 'user', `'${name}' 컬렉션으로 묶기`)
    showChatStatus(['묶을 콘텐츠 정리 중', '컬렉션에 담는 중'])
    try {
        const res = await fetch('/collections/bundle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: DEFAULT_USER_ID, name, content_ids: ids }),
        })
        const data = await res.json()
        hideChatStatus()
        if (!res.ok) throw new Error('묶기 실패')
        const aiEl = document.createElement('div')
        aiEl.className = 'chat-msg ai'
        aiEl.innerHTML = buildAIContent({
            answer: `'${name}' 컬렉션이 완성되었어요! ${data.moved}개를 담았어요.`,
            action: 'folder_created', collection_id: data.collection_id, collection_name: name,
        })
        chatMessages.appendChild(aiEl)
        loadTopFolders()
        loadCollections()
    } catch (e) {
        hideChatStatus()
        appendMsg(chatMessages, 'ai', `오류: ${e.message}`)
    } finally {
        chatMessages.scrollTop = chatMessages.scrollHeight
    }
}

async function runSummarize(ids, label) {
    const chatMessages = document.getElementById('chat-messages')
    appendMsg(chatMessages, 'user', label)
    showChatStatus('요약 중')
    try {
        const res = await fetch('/summarize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: DEFAULT_USER_ID, content_ids: ids }),
        })
        const data = await res.json()
        hideChatStatus()
        const aiEl = document.createElement('div')
        aiEl.className = 'chat-msg ai'
        aiEl.innerHTML = buildAIContent(data)
        chatMessages.appendChild(aiEl)
    } catch (e) {
        hideChatStatus()
        appendMsg(chatMessages, 'ai', `오류: ${e.message}`)
    } finally {
        chatMessages.scrollTop = chatMessages.scrollHeight
    }
}

// 다중 요약 — 콘텐츠별 (카드 + 요약) 분리 출력
function buildSummaryBlocks(summaries) {
    return summaries.map((s, i) => {
        const thumb = s.thumbnail
            ? `<img src="${s.thumbnail}" class="sum-block-thumb" onerror="this.style.display='none'" alt="" />`
            : ''
        const body = (s.summary_text || '').replace(/\n/g, '<br>')
        return `
            <div class="summary-block">
                <div class="summary-block-card">
                    ${thumb}
                    <div class="summary-block-info">
                        <div class="summary-block-title">${summaries.length > 1 ? (i + 1) + '. ' : ''}${s.title || '제목 없음'}</div>
                        <a href="${s.url}" target="_blank" class="panel-item-link">링크 열기 &rarr;</a>
                    </div>
                </div>
                <div class="summary-block-text">${body}</div>
            </div>
        `
    }).join('')
}

// AI 응답 HTML 빌드
function buildAIContent(data) {
    let html = data.answer || ''

    if (data.action === 'summary_result' && data.summaries && data.summaries.length) {
        // 답변(intro) 다음 줄바꿈 후, 콘텐츠별 요약+카드 분리
        html += buildSummaryBlocks(data.summaries)
    } else if (data.action === 'folder_select' && data.results && data.results.length) {
        // 묶기 후보 → 선택/전체 묶기
        html += buildBundleCards(data.results, data.collection_name)
    } else if (data.action === 'summarize_select' && data.results && data.results.length) {
        // 요약 대상 후보 → 복수 선택 카드 + 요약 버튼
        html += buildSelectableCards(data.results)
    } else if (data.results && data.results.length) {
        html += buildResultCards(data.results)
        // 검색 결과 → 바로 실행되는 직접 액션 버튼 (불필요한 LLM 재질문 제거)
        const ids = data.results.map(r => r.id).filter(Boolean)
        if (ids.length) {
            html += `<div class="bundle-actions" data-ids="${ids.join(',')}">
                <button class="summarize-go-btn" onclick="summarizeResults(this)">이 결과 요약하기</button>
                <button class="bundle-all-btn" onclick="bundleResults(this)">이 결과 폴더로 묶기</button>
            </div>`
        }
    }

    if (data.follow_up_questions && data.follow_up_questions.length) {
        html += `<div class="follow-up-questions">${data.follow_up_questions.map(q =>
            `<button class="follow-up-btn" onclick="followUp(this)">${q}</button>`
        ).join('')}</div>`
    }

    // 폴더 생성/이동 완료 시 → 수정(이름·리스트) 진입 아이콘 버튼
    if (data.action === 'folder_created' && data.collection_id) {
        html += `<div class="folder-edit-row">
            <button class="folder-edit-icon" title="컬렉션 수정 (이름·콘텐츠)" onclick="openCollectionPanel('${esc(data.collection_id)}','${esc(data.collection_name)}')">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>
                <span>컬렉션 수정</span>
            </button>
        </div>`
    }

    return html
}

// 후속 질문 버튼 클릭 시 채팅 입력에 삽입
// 행동 유도 버튼 클릭 → 즉시 사용자 말풍선으로 전송하고 바로 실행
window.followUp = function(btn) {
    const chatInput = document.getElementById('chat-input')
    if (!chatInput) return
    chatInput.value = btn.textContent
    sendChat()
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
    const data = await fetch(`/api/categories?user_id=${DEFAULT_USER_ID}`).then(r => r.json())
    const keys = Object.keys(data)
    if (!keys.length) {
        openModal('아카이브', '<p class="no-result">저장된 자료가 없어요.</p>')
        return
    }
    const html = keys.map(cat => `
        <div class="archive-cat">
            <div class="cat-header">
                <h3 class="cat-name">${cat}</h3>
                <button class="cat-view-btn" onclick="showArchiveItems('${esc(cat)}','')">전체 콘텐츠 &rsaquo;</button>
            </div>
            ${data[cat].map(s => `
                <div class="sub-item" onclick="showArchiveItems('${esc(cat)}','${esc(s.name)}')">
                    <span>${s.name ?? '미분류'}</span>
                    <span class="sub-right">
                        <span class="sub-count">${s.count}개 &rsaquo;</span>
                        <button class="sub-del-btn" title="중분류 삭제"
                            onclick="event.stopPropagation();deleteSubcategory('${esc(cat)}','${esc(s.name)}')">🗑</button>
                    </span>
                </div>
            `).join('')}
        </div>
    `).join('')
    openModal('아카이브', html)
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
                    <label class="arch-select">
                        <input type="checkbox" class="arch-check" value="${esc(item.id)}" />
                        <span>선택</span>
                    </label>
                    ${thumbHTML}
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
    const toolbar = data.items.length
        ? `<div class="archive-toolbar">
               <button class="archive-del-btn" onclick="deleteSelectedArchive('${esc(category)}','${esc(subcategory)}')">선택 삭제</button>
               <button class="archive-del-btn solid" onclick="deleteAllArchive('${esc(category)}','${esc(subcategory)}')">전체 삭제</button>
           </div>`
        : ''
    const title = subcategory ? `${category} / ${subcategory}` : `${category} 전체`
    openModal(title, `<button class="back-btn" onclick="showArchiveHome()">&#8592; 전체 카테고리</button>${toolbar}${cards}`)
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

// ── 아카이브 콘텐츠 복수 선택 영구 삭제 ──
window.deleteSelectedArchive = async function (category, subcategory) {
    const ids = [...document.querySelectorAll('.arch-check:checked')].map(c => c.value)
    if (!ids.length) { alert('삭제할 콘텐츠를 선택해주세요.'); return }
    if (!confirm(`선택한 ${ids.length}개 콘텐츠를 영구 삭제할까요?\n되돌릴 수 없습니다.`)) return
    await _bulkDeleteContents(ids)
    showArchiveItems(category, subcategory)
    loadTopFolders()
}

// ── 아카이브 현재 목록 전체 영구 삭제 ──
window.deleteAllArchive = async function (category, subcategory) {
    const ids = [...document.querySelectorAll('.arch-check')].map(c => c.value)
    if (!ids.length) { alert('삭제할 콘텐츠가 없어요.'); return }
    if (!confirm(`현재 목록의 ${ids.length}개 콘텐츠를 모두 영구 삭제할까요?\n되돌릴 수 없습니다.`)) return
    await _bulkDeleteContents(ids)
    showArchiveItems(category, subcategory)
    loadTopFolders()
}

// 공통 벌크 삭제 호출
async function _bulkDeleteContents(ids) {
    try {
        const res = await fetch('/contents/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: DEFAULT_USER_ID, content_ids: ids }),
        })
        if (!res.ok) throw new Error('삭제 실패')
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

// ── 이벤트 바인딩 ──
document.getElementById('btn-archives').addEventListener('click', showArchiveHome)
document.getElementById('edit-folders-btn')?.addEventListener('click', openFolderSettings)
document.getElementById('panel-reopen')?.addEventListener('click', reopenPanel)
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
    openModal('리마인더', data.deadlines.map(r => `
        <div class="reminder-item">
            <span class="reminder-deadline">마감: ${r.deadline_date}</span>
            <p class="reminder-title">${r.title}</p>
            ${r.deadline_note ? `<span class="reminder-cat">${r.deadline_note}</span>` : ''}
            <a href="${r.url}" target="_blank" class="card-link">링크 열기 &rarr;</a>
        </div>
    `).join(''))
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
    overlay.className = 'weekly-overlay'
    overlay.innerHTML = `
        <iframe src="/weekly-report" style="width:100%;height:100%;border:none;display:block;"></iframe>
    `
    document.body.appendChild(overlay)
    // 좌측에서 자연스럽게 슬라이드 인
    requestAnimationFrame(() => overlay.classList.add('open'))
})

// ── 초기 로드 ──
loadTopFolders()
loadCollections()
