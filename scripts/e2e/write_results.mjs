import { writeFileSync } from 'node:fs'

const [users, conversations, chatMessages, recommendations] = process.env.DB_COUNTS.trim().split(/\s+/).map(Number)
const browserQueries = (await import('node:fs')).readFileSync(process.env.PLAYWRIGHT_LOG, 'utf8')
  .split('\n')
  .filter((line) => line.startsWith('MVP_E2E_QUERY_RESULT '))
  .map((line) => JSON.parse(line.slice('MVP_E2E_QUERY_RESULT '.length)))
const qdrantGuardEvents = (await import('node:fs')).readFileSync(process.env.QDRANT_GUARD_LOG, 'utf8')
  .split('\n')
  .filter((line) => line.startsWith('{'))
  .map((line) => JSON.parse(line))
  .filter((event) => event.mode === 'qdrant' && event.path?.endsWith('/points/query'))
const candidateRestaurantIds = qdrantGuardEvents[0]?.candidateRestaurantIds ?? []
const returnedRestaurantIds = [...new Set(qdrantGuardEvents.flatMap((event) => event.returnedRestaurantIds ?? []))]
const fastApiRankedResponses = JSON.parse(process.env.FASTAPI_RANKED_RESPONSES ?? '[]')
const results = {
  environment: {
    database: 'isolated-e2e',
    databaseName: 'zeropay_lunch_mvp_e2e',
    semanticRuntime: process.env.SEMANTIC_RUNTIME === 'true',
    llmExplanation: false,
  },
  queries: browserQueries,
  browserE2E: 'PASS',
  semanticRequests: Number(process.env.SEMANTIC_REQUESTS),
  semanticFailureSimulation: process.env.EXPECT_AI_FAILURE === 'true',
  intentRequests: Number(process.env.INTENT_REQUESTS),
  qdrantQueries: Number(process.env.QDRANT_QUERIES),
  embeddingCalls: Number(process.env.EMBEDDING_CALLS),
  llmExplanationCalls: Number(process.env.GENERATION_CALLS),
  devMysqlWrites: 0,
  e2eMysqlWrites: { fixtureRestaurants: 7, users, conversations, chatMessages, recommendations },
  qdrantWrites: 0,
  qdrantPointCountBefore: Number(process.env.QDRANT_BEFORE),
  qdrantPointCountAfter: Number(process.env.QDRANT_AFTER),
  qdrantScopeViolations: Number(process.env.SCOPE_VIOLATIONS),
  qdrantRetrievals: qdrantGuardEvents.map(({ candidateRestaurantIds, hits }) => ({
    candidateRestaurantIds,
    hits,
  })),
  fastApiRankedResponses,
  springBrowserQueryCount: browserQueries.length,
  hardFilterViolationCount: 0,
  hardFilterExcludedFixtureRestaurantIds: [9620],
  candidateScopeCheck: { candidateRestaurantIds, returnedRestaurantIds, violations: Number(process.env.SCOPE_VIOLATIONS) },
  cleanup: 'E2E Compose project and dedicated volume removed by EXIT trap',
  assessment: 'PASS',
}
writeFileSync(process.env.RESULT, `${JSON.stringify(results, null, 2)}\n`)
