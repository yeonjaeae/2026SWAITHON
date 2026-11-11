/** Frontend-only client. Internal service keys are never sent from the browser. */
export function createSwaithonApi(baseUrl = 'http://localhost:8080') {
  const base = baseUrl.replace(/\/$/, '');
  async function request(path, { method = 'POST', json, form, signal } = {}) {
    const response = await fetch(base + path, {
      method, signal,
      headers: json === undefined ? {} : { 'Content-Type': 'application/json' },
      body: form ?? (json === undefined ? undefined : JSON.stringify(json)),
    });
    const text = await response.text();
    let result;
    try { result = text ? JSON.parse(text) : null; } catch { result = { detail: text }; }
    if (!response.ok) {
      const error = new Error(typeof result?.detail === 'string' ? result.detail : `API 오류 (${response.status})`);
      error.status = response.status;
      error.detail = result?.detail ?? result;
      throw error;
    }
    return result;
  }
  return {
    status: (signal) => request('/api/status', { method: 'GET', signal }),
    demo: (signal) => request('/api/recommendations/demo', { method: 'GET', signal }),
    analyzeImage: ({ image, worldFile, region, imageCrs = 'EPSG:3857', signal }) => {
      const form = new FormData();
      form.append('image', image);
      form.append('world_file', worldFile);
      form.append('region', JSON.stringify(region));
      form.append('image_crs', imageCrs);
      return request('/api/ai/landcover', { form, signal });
    },
    analyzeRegion: (analysis, signal) => request('/api/region/analyze', { json: analysis, signal }),
    recommend: ({ analysis, options = {} }, signal) => request('/api/workflows/recommend', { json: { analysis, options }, signal }),
    select: (recommendationId, candidateId, signal) => request('/api/recommendations/select', {
      json: { recommendation_id: recommendationId, candidate_id: candidateId }, signal,
    }),
    calculateDesign: (input, signal) => request('/api/workflows/design', { json: input, signal }),
  };
}
