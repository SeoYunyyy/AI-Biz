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
"[project]/app/api/chat/route.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
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
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$openai$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/openai.ts [app-route] (ecmascript)");
;
;
;
const runtime = 'nodejs';
const maxDuration = 30;
const admin = ()=>(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f40$supabase$2f$supabase$2d$js$2f$dist$2f$index$2e$mjs__$5b$app$2d$route$5d$__$28$ecmascript$29$__$3c$locals$3e$__["createClient"])(("TURBOPACK compile-time value", "https://uwroxndwnzojfbjmpfcb.supabase.co"), process.env.SUPABASE_SERVICE_ROLE_KEY);
// ── 벡터 유사도 (코사인) ────────────────────────────────────────
function cosine(a, b) {
    let dot = 0, na = 0, nb = 0;
    for(let i = 0; i < a.length; i++){
        dot += a[i] * b[i];
        na += a[i] * a[i];
        nb += b[i] * b[i];
    }
    const d = Math.sqrt(na) * Math.sqrt(nb);
    return d === 0 ? 0 : dot / d;
}
function parseVector(v) {
    if (Array.isArray(v)) return v;
    if (typeof v === 'string') return v.replace(/[\[\]]/g, '').split(',').map(Number);
    return [];
}
// ── 의도 감지 ───────────────────────────────────────────────────
function detectMode(query) {
    if (/예전에|전에|몇 달|며칠|지난|그때|기억|봤던|저장했던|뭐였더라|있었는데/.test(query)) return 'memory';
    if (/보여줘|추천|찾아줘|컬렉션|모아|모음|폴더|목록|어때/.test(query)) return 'collection';
    return 'general';
}
// ── 폴백: 수동 벡터 검색 ────────────────────────────────────────
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function manualSearch(db, userId, queryEmbedding, limit = 5) {
    // 1. 이 유저의 모든 임베딩 가져오기
    const { data: embedRows, error: embedError } = await db.from('embeddings').select('content_id, embedding');
    if (embedError || !embedRows?.length) {
        // embeddings 테이블이 없거나 비어있으면 텍스트 기반 최신순 반환
        const { data: fallback } = await db.from('contents').select('id, url, content_type, title, thumbnail_url, author, metadata, hashtags, topics, moods, collection_id, saved_at').eq('user_id', userId).order('saved_at', {
            ascending: false
        }).limit(limit);
        return (fallback || []).map((c)=>toCard(c, 1));
    }
    const scored = embedRows.map((row)=>({
            content_id: row.content_id,
            score: cosine(queryEmbedding, parseVector(row.embedding))
        })).sort((a, b)=>b.score - a.score).slice(0, limit);
    if (!scored.length) return [];
    // 3. 상위 content_id로 contents 조회 (user_id 필터 포함)
    const topIds = scored.map((s)=>s.content_id);
    const { data: contents } = await db.from('contents').select('id, url, content_type, title, thumbnail_url, author, metadata, hashtags, topics, moods, collection_id, saved_at').eq('user_id', userId).in('id', topIds);
    if (!contents?.length) return [];
    return contents.map((c)=>toCard(c, scored.find((s)=>s.content_id === c.id)?.score ?? 0)).sort((a, b)=>(b.similarity ?? 0) - (a.similarity ?? 0));
}
// ── 컬렉션 의도 처리 ─────────────────────────────────────────────
// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function findBestCollection(db, userId, query, queryEmbedding) {
    const { data: collections } = await db.from('collections').select('id, name, emoji, content_count, cluster_centroid').eq('user_id', userId).order('content_count', {
        ascending: false
    });
    if (!collections?.length) return null;
    // 텍스트 매칭 먼저
    const queryLower = query.toLowerCase();
    const textMatch = collections.find((c)=>queryLower.includes(c.name.toLowerCase()) || c.name.toLowerCase().split(' ').some((w)=>queryLower.includes(w)));
    if (textMatch) return textMatch;
    const scored = collections.map((c)=>{
        const centroid = parseVector(c.cluster_centroid);
        return {
            col: c,
            score: centroid.length > 0 ? cosine(queryEmbedding, centroid) : 0
        };
    }).sort((a, b)=>b.score - a.score);
    return scored[0]?.score > 0.35 ? scored[0].col : collections[0];
}
function toCard(c, similarity) {
    return {
        id: c.id,
        url: c.url,
        content_type: c.content_type,
        title: c.title || '제목 없음',
        thumbnail_url: c.thumbnail_url,
        author: c.author,
        metadata: c.metadata,
        hashtags: c.hashtags || [],
        topics: c.topics || [],
        moods: c.moods || [],
        collection_id: c.collection_id,
        saved_at: c.saved_at,
        similarity
    };
}
function getCardLabel(index, similarity, savedAt) {
    if (index === 0) return '가장 가능성 높은 매칭';
    const daysSinceSaved = Math.floor((Date.now() - new Date(savedAt).getTime()) / (1000 * 60 * 60 * 24));
    if (index === 1) return daysSinceSaved < 14 ? '비슷한 시기에 저장한 콘텐츠' : '비슷한 분위기의 콘텐츠';
    return similarity > 0.6 ? '혹시 이건 어때요?' : '같은 분위기인데 한참 안 보신 거예요';
}
async function POST(req) {
    try {
        const { query, userId } = await req.json();
        if (!query || !userId) {
            return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
                error: 'query와 userId가 필요합니다.'
            }, {
                status: 400
            });
        }
        const db = admin();
        // 콘텐츠 수 확인 — analysis_status 필터 없이 (관대하게)
        const { count, error: countError } = await db.from('contents').select('*', {
            count: 'exact',
            head: true
        }).eq('user_id', userId);
        if (countError) {
            console.error('count error:', countError);
        }
        if ((count ?? 0) === 0) {
            return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
                message: '아직 저장된 콘텐츠가 없어요. 아래 + 버튼으로 유튜브나 블로그 링크를 저장해보세요!',
                cards: [],
                mode: 'general',
                collectionData: null
            });
        }
        // 쿼리 임베딩 생성
        const queryEmbedding = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$openai$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["generateEmbedding"])(query);
        const mode = detectMode(query);
        // ── 컬렉션 모드 ──────────────────────────────────────────────
        if (mode === 'collection') {
            const bestCol = await findBestCollection(db, userId, query, queryEmbedding);
            if (bestCol) {
                // 해당 컬렉션의 콘텐츠 가져오기
                const { data: colContents } = await db.from('contents').select('id, url, content_type, title, thumbnail_url, author, metadata, hashtags, topics, moods, collection_id, saved_at').eq('collection_id', bestCol.id).eq('user_id', userId).order('saved_at', {
                    ascending: false
                }).limit(10);
                const cards = (colContents || []).map((c)=>toCard(c, 1));
                return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
                    message: `${bestCol.emoji} ${bestCol.name} 컬렉션에 ${bestCol.content_count || cards.length}개가 있어요!`,
                    cards: cards.slice(0, 5),
                    mode: 'collection',
                    collectionData: {
                        id: bestCol.id,
                        name: bestCol.name,
                        emoji: bestCol.emoji,
                        content_count: bestCol.content_count || cards.length
                    }
                });
            }
        }
        // ── 기억 회수 / 일반 모드 ─────────────────────────────────────
        let cards = [];
        // 1순위: RPC 함수 시도
        const { data: rpcResults, error: rpcError } = await db.rpc('match_user_contents', {
            query_embedding: JSON.stringify(queryEmbedding),
            user_id_param: userId,
            match_count: 5
        });
        if (!rpcError && rpcResults?.length) {
            cards = rpcResults.slice(0, 3).map((r, i)=>({
                    ...toCard(r, r.similarity),
                    label: getCardLabel(i, r.similarity, r.saved_at)
                }));
        } else {
            // 2순위: 수동 벡터 검색 폴백
            if (rpcError) console.error('RPC error (using fallback):', rpcError.message);
            const fallbackCards = await manualSearch(db, userId, queryEmbedding, 5);
            cards = fallbackCards.slice(0, 3).map((c, i)=>({
                    ...c,
                    label: getCardLabel(i, c.similarity ?? 0, c.saved_at)
                }));
        }
        const message = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$openai$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["generateChatResponse"])(query, cards);
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            message,
            cards,
            mode,
            collectionData: null
        });
    } catch (err) {
        console.error('chat error:', err);
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            error: '서버 오류'
        }, {
            status: 500
        });
    }
}
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__0luflx_._.js.map