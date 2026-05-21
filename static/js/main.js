const promptInput = document.getElementById('prompt-input')
const submitBtn   = document.getElementById('submit-btn')
const resultsDiv  = document.getElementById('results')
const modal       = document.getElementById('modal')
const modalBody   = document.getElementById('modal-body')

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

// 결과 카드 HTML 생성 (content_type에 따라 요약 노출 여부 결정)
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

async function handleSubmit() {
    const text = promptInput.value.trim()
    if (!text) return

    setLoading(true)

    try {
        if (isURL(text.split(' ')[0])) {
            // URL 저장 모드
            const { url, deadline } = parseInput(text)
            const res  = await fetch('/api/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, deadline })
            })
            const data = await res.json()
            if (!res.ok || data.error) throw new Error(data.error || `서버 오류 (${res.status})`)
            showResults(buildCard(data.item, true))
        } else {
            // 자연어 검색 모드
            const res  = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: text })
            })
            if (!res.ok) throw new Error(`서버 오류 (${res.status})`)
            const data = await res.json()
            if (!data.results.length) {
                showResults('<p class="no-result">관련 자료를 찾지 못했어요.</p>')
            } else {
                showResults(data.results.map(r => buildCard(r)).join(''))
            }
        }
    } catch (e) {
        showResults(`<p class="error-msg">${e.message}</p>`)
    } finally {
        setLoading(false)
        promptInput.value = ''
    }
}

// 모달 열기/닫기
function openModal(title, content) {
    modalBody.innerHTML = `<h2 class="modal-title">${title}</h2>${content}`
    modal.classList.add('open')
}

function closeModal() {
    modal.classList.remove('open')
}

// 아카이브 — 카테고리 목록 화면
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
                <div class="sub-item" onclick="showArchiveItems('${escHtml(cat)}', '${escHtml(s.name)}')">
                    <span>${s.name ?? '미분류'}</span>
                    <span class="sub-count">${s.count}개 &rsaquo;</span>
                </div>
            `).join('')}
        </div>
    `).join('')
    openModal('아카이브', html)
}

// 아카이브 — 서브카테고리 아이템 목록 화면
async function showArchiveItems(category, subcategory) {
    const params = new URLSearchParams({ category, subcategory })
    const data = await fetch(`/api/items?${params}`).then(r => r.json())

    const cardsHtml = data.items.length
        ? data.items.map(item => {
            const showSummary = item.content_type !== 'music' && item.summary
            const tags = Array.isArray(item.tags) ? item.tags : []
            const date = item.created_at ? item.created_at.slice(0, 10) : ''
            return `
                <div class="archive-item-card">
                    ${showSummary ? `<p class="archive-item-summary">${item.summary}</p>` : ''}
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

    const backBtn = `<button class="back-btn" onclick="showArchiveHome()">&#8592; 전체 카테고리</button>`
    openModal(`${category} / ${subcategory}`, backBtn + cardsHtml)
}

function escHtml(str) {
    return (str ?? '').toString().replace(/'/g, "\\'")
}

document.getElementById('btn-archives').addEventListener('click', showArchiveHome)

// 리마인더 모달
document.getElementById('btn-reminders').addEventListener('click', async () => {
    const data = await fetch('/api/reminders').then(r => r.json())
    if (!data.length) {
        openModal('리마인더', '<p class="no-result">3일 이내 마감 자료가 없어요.</p>')
        return
    }
    const html = data.map(r => `
        <div class="reminder-item">
            <span class="reminder-deadline">마감: ${r.deadline}</span>
            <p class="reminder-title">${r.title}</p>
            <span class="reminder-cat">${r.category}</span>
            <a href="${r.url}" target="_blank" class="card-link">링크 열기 &rarr;</a>
        </div>
    `).join('')
    openModal('리마인더', html)
})

// 월간 레포트 모달
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

// 닫기 이벤트
document.getElementById('modal-close').addEventListener('click', closeModal)
modal.addEventListener('click', e => { if (e.target === modal) closeModal() })

// 입력 이벤트
submitBtn.addEventListener('click', handleSubmit)
promptInput.addEventListener('keydown', e => { if (e.key === 'Enter') handleSubmit() })

// URL 입력 시 저장, 자연어 입력 시 검색 / 네비게이션 버튼으로 아카이브·리마인더·월간 레포트 모달 표시
