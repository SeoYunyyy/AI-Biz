module.exports = [
"[externals]/next/dist/compiled/next-server/app-route-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-route-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/@opentelemetry/api [external] (next/dist/compiled/@opentelemetry/api, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/@opentelemetry/api", () => require("next/dist/compiled/@opentelemetry/api"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-unit-async-storage.external.js [external] (next/dist/server/app-render/work-unit-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-unit-async-storage.external.js", () => require("next/dist/server/app-render/work-unit-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-async-storage.external.js [external] (next/dist/server/app-render/work-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-async-storage.external.js", () => require("next/dist/server/app-render/work-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/shared/lib/no-fallback-error.external.js [external] (next/dist/shared/lib/no-fallback-error.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/shared/lib/no-fallback-error.external.js", () => require("next/dist/shared/lib/no-fallback-error.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/after-task-async-storage.external.js [external] (next/dist/server/app-render/after-task-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/after-task-async-storage.external.js", () => require("next/dist/server/app-render/after-task-async-storage.external.js"));

module.exports = mod;
}),
"[project]/lib/youtube.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "extractYouTubeId",
    ()=>extractYouTubeId,
    "fetchYouTubeMetadata",
    ()=>fetchYouTubeMetadata,
    "isYouTubeUrl",
    ()=>isYouTubeUrl
]);
function extractYouTubeId(url) {
    const patterns = [
        /youtube\.com\/watch\?v=([^&]+)/,
        /youtu\.be\/([^?]+)/,
        /youtube\.com\/embed\/([^?]+)/,
        /youtube\.com\/shorts\/([^?]+)/
    ];
    for (const pattern of patterns){
        const match = url.match(pattern);
        if (match) return match[1];
    }
    return null;
}
function isYouTubeUrl(url) {
    return /youtube\.com|youtu\.be/.test(url);
}
async function fetchYouTubeMetadata(url) {
    const videoId = extractYouTubeId(url);
    if (!videoId) throw new Error('유효하지 않은 YouTube URL입니다.');
    const apiKey = process.env.YOUTUBE_API_KEY;
    if (!apiKey) throw new Error('YouTube API 키가 없습니다.');
    const apiUrl = `https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails&id=${videoId}&key=${apiKey}`;
    const res = await fetch(apiUrl);
    if (!res.ok) throw new Error(`YouTube API 오류: ${res.status}`);
    const data = await res.json();
    if (!data.items || data.items.length === 0) {
        throw new Error('영상을 찾을 수 없습니다.');
    }
    const snippet = data.items[0].snippet;
    const contentDetails = data.items[0].contentDetails;
    const title = snippet.title || '';
    const description = snippet.description || '';
    const channelName = snippet.channelTitle || '';
    const thumbnail = snippet.thumbnails?.maxres?.url || snippet.thumbnails?.high?.url || snippet.thumbnails?.medium?.url || `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
    const rawText = [
        title,
        description
    ].filter(Boolean).join('\n\n');
    return {
        title,
        description: description.slice(0, 500),
        thumbnail_url: thumbnail,
        author: channelName,
        metadata: {
            channel_name: channelName,
            video_id: videoId,
            duration: contentDetails?.duration || null
        },
        raw_text: rawText,
        content_type: 'youtube'
    };
}
}),
"[project]/lib/crawler.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "crawlContent",
    ()=>crawlContent
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$youtube$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/youtube.ts [app-route] (ecmascript)");
;
async function crawlContent(url) {
    if ((0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$youtube$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["isYouTubeUrl"])(url)) {
        return (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$youtube$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["fetchYouTubeMetadata"])(url);
    }
    return crawlBlog(url);
}
async function crawlBlog(url) {
    const res = await fetch(url, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            Accept: 'text/html,application/xhtml+xml',
            'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8'
        },
        signal: AbortSignal.timeout(10000)
    });
    if (!res.ok) throw new Error(`페이지 로드 실패: ${res.status}`);
    const html = await res.text();
    const title = extractTitle(html);
    const description = extractDescription(html);
    const thumbnail_url = extractThumbnail(html, url);
    const author = extractAuthor(html);
    const siteName = extractSiteName(html);
    const raw_text = extractText(html);
    return {
        title,
        description,
        thumbnail_url,
        author,
        metadata: {
            site_name: siteName,
            source_url: url
        },
        raw_text,
        content_type: 'blog'
    };
}
function extractTitle(html) {
    const ogTitle = html.match(/<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)["']/i);
    if (ogTitle) return decode(ogTitle[1]);
    const titleTag = html.match(/<title[^>]*>([^<]+)<\/title>/i);
    if (titleTag) return decode(titleTag[1].trim());
    const h1 = html.match(/<h1[^>]*>([^<]+)<\/h1>/i);
    if (h1) return decode(h1[1].trim());
    return 'Untitled';
}
function extractDescription(html) {
    const ogDesc = html.match(/<meta[^>]+property=["']og:description["'][^>]+content=["']([^"']{1,500})["']/i);
    if (ogDesc) return decode(ogDesc[1]);
    const metaDesc = html.match(/<meta[^>]+name=["']description["'][^>]+content=["']([^"']{1,500})["']/i);
    if (metaDesc) return decode(metaDesc[1]);
    return '';
}
function extractThumbnail(html, baseUrl) {
    const ogImg = html.match(/<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']/i);
    if (ogImg) {
        const src = ogImg[1];
        if (src.startsWith('http')) return src;
        try {
            return new URL(src, baseUrl).href;
        } catch  {
            return null;
        }
    }
    return null;
}
function extractAuthor(html) {
    const ogAuthor = html.match(/<meta[^>]+property=["']article:author["'][^>]+content=["']([^"']+)["']/i);
    if (ogAuthor) return decode(ogAuthor[1]);
    const metaAuthor = html.match(/<meta[^>]+name=["']author["'][^>]+content=["']([^"']+)["']/i);
    if (metaAuthor) return decode(metaAuthor[1]);
    return null;
}
function extractSiteName(html) {
    const ogSite = html.match(/<meta[^>]+property=["']og:site_name["'][^>]+content=["']([^"']+)["']/i);
    return ogSite ? decode(ogSite[1]) : null;
}
function extractText(html) {
    let text = html.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, ' ').replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, ' ').replace(/<nav\b[^<]*(?:(?!<\/nav>)<[^<]*)*<\/nav>/gi, ' ').replace(/<header\b[^<]*(?:(?!<\/header>)<[^<]*)*<\/header>/gi, ' ').replace(/<footer\b[^<]*(?:(?!<\/footer>)<[^<]*)*<\/footer>/gi, ' ');
    const paragraphs = [];
    const pMatches = text.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/gi);
    for (const m of pMatches){
        const clean = m[1].replace(/<[^>]+>/g, '').trim();
        if (clean.length > 20) paragraphs.push(decode(clean));
    }
    if (paragraphs.length > 0) return paragraphs.join('\n').slice(0, 8000);
    return decode(text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()).slice(0, 8000);
}
function decode(str) {
    return str.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ').trim();
}
}),
"[project]/lib/openai.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "analyzeContent",
    ()=>analyzeContent,
    "formatTimeAgo",
    ()=>formatTimeAgo,
    "generateChatResponse",
    ()=>generateChatResponse,
    "generateCollectionName",
    ()=>generateCollectionName,
    "generateEmbedding",
    ()=>generateEmbedding
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$openai$2f$index$2e$mjs__$5b$app$2d$route$5d$__$28$ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i("[project]/node_modules/openai/index.mjs [app-route] (ecmascript) <locals>");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$openai$2f$client$2e$mjs__$5b$app$2d$route$5d$__$28$ecmascript$29$__$3c$export__OpenAI__as__default$3e$__ = __turbopack_context__.i("[project]/node_modules/openai/client.mjs [app-route] (ecmascript) <export OpenAI as default>");
;
let _client = null;
function getClient() {
    if (!_client) {
        _client = new __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$openai$2f$client$2e$mjs__$5b$app$2d$route$5d$__$28$ecmascript$29$__$3c$export__OpenAI__as__default$3e$__["default"]({
            apiKey: process.env.OPENAI_API_KEY
        });
    }
    return _client;
}
async function analyzeContent(text, title, type) {
    const ai = getClient();
    const truncatedText = text.slice(0, 4000);
    const response = await ai.chat.completions.create({
        model: 'gpt-4o-mini',
        messages: [
            {
                role: 'system',
                content: '콘텐츠 분석 전문가입니다. JSON만 반환하세요.'
            },
            {
                role: 'user',
                content: `다음 ${type} 콘텐츠를 분석하세요.

제목: ${title}
내용: ${truncatedText}

JSON 형식으로만 응답:
{
  "topics": ["topic1", "topic2"],
  "moods": ["mood1", "mood2"],
  "intent": ["intent1"],
  "energy": "low" | "medium" | "high",
  "format": "${type}",
  "hashtags": ["#한글태그1", "#한글태그2", "#한글태그3"]
}

- topics/moods/intent: 영어 소문자, 1~3개
- hashtags: 한국어 #태그 형식, 3~5개`
            }
        ],
        response_format: {
            type: 'json_object'
        },
        temperature: 0.3,
        max_tokens: 300
    });
    const raw = JSON.parse(response.choices[0].message.content || '{}');
    let compressed_text = text;
    if (text.length > 2000) {
        const sumRes = await ai.chat.completions.create({
            model: 'gpt-4o-mini',
            messages: [
                {
                    role: 'system',
                    content: '주어진 텍스트를 핵심만 500자 이내 한국어로 요약하세요.'
                },
                {
                    role: 'user',
                    content: text.slice(0, 8000)
                }
            ],
            temperature: 0.3,
            max_tokens: 400
        });
        compressed_text = sumRes.choices[0].message.content || text.slice(0, 500);
    }
    return {
        topics: Array.isArray(raw.topics) ? raw.topics.slice(0, 3) : [],
        moods: Array.isArray(raw.moods) ? raw.moods.slice(0, 3) : [],
        intent: Array.isArray(raw.intent) ? raw.intent.slice(0, 2) : [],
        energy: [
            'low',
            'medium',
            'high'
        ].includes(raw.energy) ? raw.energy : 'medium',
        format: raw.format || type,
        hashtags: Array.isArray(raw.hashtags) ? raw.hashtags.slice(0, 5) : [],
        compressed_text
    };
}
async function generateCollectionName(topics, moods, sampleTitles) {
    const ai = getClient();
    const response = await ai.chat.completions.create({
        model: 'gpt-4o',
        messages: [
            {
                role: 'system',
                content: '감성적인 콘텐츠 컬렉션 이름을 만드는 전문가입니다. JSON만 반환하세요.'
            },
            {
                role: 'user',
                content: `다음 특성의 콘텐츠 컬렉션 이름과 이모지를 만드세요.
주제: ${topics.join(', ')}
분위기: ${moods.join(', ')}
콘텐츠 예시: ${sampleTitles.slice(0, 3).join(', ')}

JSON:
{
  "name": "감성적인 한국어 이름 (2~5단어)",
  "emoji": "어울리는 이모지 1개"
}`
            }
        ],
        response_format: {
            type: 'json_object'
        },
        temperature: 0.8,
        max_tokens: 80
    });
    const result = JSON.parse(response.choices[0].message.content || '{}');
    return {
        name: result.name || '새 컬렉션',
        emoji: result.emoji || '📁'
    };
}
async function generateChatResponse(query, matchedCards) {
    if (matchedCards.length === 0) {
        return '아직 저장된 콘텐츠가 없어요. 아래 + 버튼으로 유튜브나 블로그 링크를 저장해보세요!';
    }
    const ai = getClient();
    const cardList = matchedCards.map((c, i)=>`[${i + 1}] "${c.title || '제목 없음'}" (${formatTimeAgo(c.saved_at)})`).join('\n');
    const response = await ai.chat.completions.create({
        model: 'gpt-4o',
        messages: [
            {
                role: 'system',
                content: `사용자의 콘텐츠 라이브러리 도우미입니다. 찾던 콘텐츠를 자연스럽고 따뜻하게 안내하세요.
"이거 아닐까요?" 같은 편안한 말투로 1~2문장만 답하세요.`
            },
            {
                role: 'user',
                content: `사용자 질문: "${query}"\n\n관련 콘텐츠:\n${cardList}\n\n짧고 자연스럽게 안내해주세요.`
            }
        ],
        temperature: 0.7,
        max_tokens: 80
    });
    return response.choices[0].message.content || '이런 콘텐츠를 찾고 계신 것 같아요!';
}
async function generateEmbedding(text) {
    const ai = getClient();
    const response = await ai.embeddings.create({
        model: 'text-embedding-3-small',
        input: text.slice(0, 8000)
    });
    return response.data[0].embedding;
}
function formatTimeAgo(dateStr) {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays < 1) return '오늘';
    if (diffDays < 7) return `${diffDays}일 전`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)}주 전`;
    if (diffDays < 365) return `${Math.floor(diffDays / 30)}개월 전`;
    return `${Math.floor(diffDays / 365)}년 전`;
}
}),
"[project]/lib/clustering.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "runClustering",
    ()=>runClustering
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f40$supabase$2f$supabase$2d$js$2f$dist$2f$index$2e$mjs__$5b$app$2d$route$5d$__$28$ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i("[project]/node_modules/@supabase/supabase-js/dist/index.mjs [app-route] (ecmascript) <locals>");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$openai$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/openai.ts [app-route] (ecmascript)");
;
;
const MIN_CLUSTER_SIZE = 3;
const SIMILARITY_THRESHOLD = 0.40;
function cosine(a, b) {
    let dot = 0, na = 0, nb = 0;
    for(let i = 0; i < a.length; i++){
        dot += a[i] * b[i];
        na += a[i] * a[i];
        nb += b[i] * b[i];
    }
    const denom = Math.sqrt(na) * Math.sqrt(nb);
    return denom === 0 ? 0 : dot / denom;
}
function parseVector(v) {
    if (Array.isArray(v)) return v;
    if (typeof v === 'string') {
        return v.replace(/[\[\]]/g, '').split(',').map(Number);
    }
    return [];
}
function dbscan(rows) {
    const n = rows.length;
    const labels = new Map(rows.map((r)=>[
            r.content_id,
            -1
        ]));
    const visited = new Set();
    let clusterIdx = 0;
    const getNeighbors = (idx)=>rows.map((_, j)=>j).filter((j)=>j !== idx && cosine(rows[idx].embedding, rows[j].embedding) >= SIMILARITY_THRESHOLD);
    for(let i = 0; i < n; i++){
        const row = rows[i];
        if (visited.has(row.content_id)) continue;
        visited.add(row.content_id);
        const nbrs = getNeighbors(i);
        if (nbrs.length < MIN_CLUSTER_SIZE - 1) continue;
        labels.set(row.content_id, clusterIdx);
        const queue = [
            ...nbrs
        ];
        while(queue.length > 0){
            const j = queue.pop();
            const jRow = rows[j];
            if (!visited.has(jRow.content_id)) {
                visited.add(jRow.content_id);
                const jNbrs = getNeighbors(j);
                if (jNbrs.length >= MIN_CLUSTER_SIZE - 1) queue.push(...jNbrs);
            }
            if (labels.get(jRow.content_id) === -1) {
                labels.set(jRow.content_id, clusterIdx);
            }
        }
        clusterIdx++;
    }
    return labels;
}
async function runClustering(userId) {
    const db = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f40$supabase$2f$supabase$2d$js$2f$dist$2f$index$2e$mjs__$5b$app$2d$route$5d$__$28$ecmascript$29$__$3c$locals$3e$__["createClient"])(("TURBOPACK compile-time value", "https://uwroxndwnzojfbjmpfcb.supabase.co"), process.env.SUPABASE_SERVICE_ROLE_KEY);
    // Step 1: 이 유저의 분석 완료 콘텐츠 ID + 메타 조회
    const { data: userContents, error: contentsError } = await db.from('contents').select('id, title, topics, moods').eq('user_id', userId).eq('analysis_status', 'completed');
    if (contentsError || !userContents || userContents.length < MIN_CLUSTER_SIZE) return;
    const contentIds = userContents.map((c)=>c.id);
    // Step 2: 해당 ID들의 임베딩 조회
    const { data: embedRows, error: embedError } = await db.from('embeddings').select('content_id, embedding').in('content_id', contentIds);
    if (embedError || !embedRows?.length) return;
    const metaMap = new Map(userContents.map((c)=>[
            c.id,
            {
                title: c.title,
                topics: c.topics || [],
                moods: c.moods || []
            }
        ]));
    const parsed = embedRows.map((r)=>{
        const meta = metaMap.get(r.content_id);
        if (!meta) return null;
        const embedding = parseVector(r.embedding);
        if (embedding.length === 0) return null;
        return {
            content_id: r.content_id,
            embedding,
            title: meta.title,
            topics: meta.topics,
            moods: meta.moods
        };
    }).filter((r)=>r !== null);
    if (parsed.length < MIN_CLUSTER_SIZE) return;
    const labels = dbscan(parsed);
    // 클러스터별 그룹핑
    const clusters = new Map();
    for (const row of parsed){
        const label = labels.get(row.content_id) ?? -1;
        if (label === -1) continue;
        if (!clusters.has(label)) clusters.set(label, []);
        clusters.get(label).push(row);
    }
    // 기존 자동 생성 컬렉션 삭제 — CASCADE 위험 방지: update 확인 후 delete
    const { data: oldCols } = await db.from('collections').select('id').eq('user_id', userId).eq('is_user_renamed', false);
    if (oldCols && oldCols.length > 0) {
        const oldIds = oldCols.map((c)=>c.id);
        // 1) 콘텐츠 연결 해제 — 반드시 error 확인
        const { error: unlinkError } = await db.from('contents').update({
            collection_id: null
        }).in('collection_id', oldIds).eq('user_id', userId);
        if (unlinkError) {
            console.error('collection unlink failed, aborting delete to prevent data loss:', unlinkError);
            return;
        }
        // 2) 연결 해제 확인 후 컬렉션 삭제
        await db.from('collections').delete().eq('user_id', userId).in('id', oldIds);
    }
    // 새 컬렉션 생성
    for (const [, members] of clusters){
        if (members.length < MIN_CLUSTER_SIZE) continue;
        const allTopics = members.flatMap((m)=>m.topics);
        const allMoods = members.flatMap((m)=>m.moods);
        const topTopics = mostFrequent(allTopics, 3);
        const topMoods = mostFrequent(allMoods, 3);
        const sampleTitles = members.slice(0, 3).map((m)=>m.title || '').filter(Boolean);
        const { name, emoji } = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$openai$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["generateCollectionName"])(topTopics, topMoods, sampleTitles);
        // 클러스터 중심(centroid) 임베딩 계산
        const centroidText = [
            ...topTopics,
            ...topMoods
        ].join(' ') || sampleTitles[0] || 'collection';
        const centroidEmbedding = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$openai$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["generateEmbedding"])(centroidText);
        // 컬렉션 생성
        const { data: col } = await db.from('collections').insert({
            user_id: userId,
            name,
            emoji,
            is_user_renamed: false,
            content_count: members.length,
            cluster_centroid: JSON.stringify(centroidEmbedding)
        }).select('id').single();
        if (!col) continue;
        // contents.collection_id 업데이트 (1:N)
        await db.from('contents').update({
            collection_id: col.id
        }).in('id', members.map((m)=>m.content_id));
    }
}
function mostFrequent(arr, topN) {
    const freq = new Map();
    for (const item of arr)freq.set(item, (freq.get(item) || 0) + 1);
    return [
        ...freq.entries()
    ].sort((a, b)=>b[1] - a[1]).slice(0, topN).map(([k])=>k);
}
}),
"[project]/app/api/ingest/route.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "POST",
    ()=>POST,
    "maxDuration",
    ()=>maxDuration,
    "runtime",
    ()=>runtime
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/server.js [app-route] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f40$supabase$2f$supabase$2d$js$2f$dist$2f$index$2e$mjs__$5b$app$2d$route$5d$__$28$ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i("[project]/node_modules/@supabase/supabase-js/dist/index.mjs [app-route] (ecmascript) <locals>");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$crawler$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/crawler.ts [app-route] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$openai$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/openai.ts [app-route] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$clustering$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/clustering.ts [app-route] (ecmascript)");
;
;
;
;
;
const runtime = 'nodejs';
const maxDuration = 60;
const admin = ()=>(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f40$supabase$2f$supabase$2d$js$2f$dist$2f$index$2e$mjs__$5b$app$2d$route$5d$__$28$ecmascript$29$__$3c$locals$3e$__["createClient"])(("TURBOPACK compile-time value", "https://uwroxndwnzojfbjmpfcb.supabase.co"), process.env.SUPABASE_SERVICE_ROLE_KEY);
async function POST(req) {
    try {
        const { url, userId } = await req.json();
        if (!url || !userId) {
            return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
                error: 'url과 userId가 필요합니다.'
            }, {
                status: 400
            });
        }
        const db = admin();
        // 중복 URL 체크 (UNIQUE constraint: user_id + url)
        const { data: existing } = await db.from('contents').select('id, title, hashtags, analysis_status').eq('user_id', userId).eq('url', url).single();
        if (existing) {
            return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
                duplicate: true,
                content: existing
            });
        }
        // 1. 즉시 저장 (분석 전 — 사용자를 기다리게 하지 않음)
        const { data: saved, error: saveError } = await db.from('contents').insert({
            user_id: userId,
            url,
            content_type: 'other',
            analysis_status: 'processing',
            saved_at: new Date().toISOString()
        }).select('id').single();
        if (saveError || !saved) {
            return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
                error: '저장 실패'
            }, {
                status: 500
            });
        }
        const contentId = saved.id;
        try {
            // 2. 크롤링
            const crawled = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$crawler$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["crawlContent"])(url);
            // 3. AI 분석
            const analysisText = crawled.raw_text || crawled.description || crawled.title || '';
            const analysis = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$openai$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["analyzeContent"])(analysisText, crawled.title, crawled.content_type);
            // 4. 임베딩 생성
            const embeddingInput = [
                crawled.title,
                analysis.topics.join(' '),
                analysis.moods.join(' '),
                analysis.compressed_text
            ].filter(Boolean).join(' ');
            const embedding = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$openai$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["generateEmbedding"])(embeddingInput);
            // 5. contents 업데이트
            await db.from('contents').update({
                content_type: crawled.content_type,
                title: crawled.title,
                description: crawled.description,
                thumbnail_url: crawled.thumbnail_url,
                author: crawled.author,
                metadata: crawled.metadata,
                topics: analysis.topics,
                moods: analysis.moods,
                intent: analysis.intent,
                energy: analysis.energy,
                hashtags: analysis.hashtags,
                analysis_status: 'completed',
                analyzed_at: new Date().toISOString()
            }).eq('id', contentId);
            // 6. embeddings 테이블에 별도 저장
            await db.from('embeddings').insert({
                content_id: contentId,
                embedding: JSON.stringify(embedding)
            });
            // 7. 완료된 콘텐츠 수 확인 → 30개 이상이면 클러스터링
            const { count } = await db.from('contents').select('*', {
                count: 'exact',
                head: true
            }).eq('user_id', userId).eq('analysis_status', 'completed');
            if ((count ?? 0) >= 30) {
                (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$clustering$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["runClustering"])(userId).catch(console.error);
            }
            return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
                id: contentId,
                title: crawled.title,
                thumbnail_url: crawled.thumbnail_url,
                content_type: crawled.content_type,
                hashtags: analysis.hashtags,
                metadata: crawled.metadata,
                analysis_status: 'completed'
            });
        } catch (analysisError) {
            console.error('analysis error:', analysisError);
            await db.from('contents').update({
                analysis_status: 'failed'
            }).eq('id', contentId);
            return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
                error: '분석 실패',
                contentId
            }, {
                status: 500
            });
        }
    } catch (err) {
        console.error('ingest error:', err);
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            error: '서버 오류'
        }, {
            status: 500
        });
    }
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__0tkqv60._.js.map