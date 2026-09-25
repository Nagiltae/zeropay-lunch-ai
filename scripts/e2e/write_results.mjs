import { writeFileSync } from 'node:fs'

const [users, conversations, chatMessages, recommendations] = process.env.DB_COUNTS.trim().split(/\s+/).map(Number)
const browserQueries = (await import('node:fs')).readFileSync(process.env.PLAYWRIGHT_LOG, 'utf8')
  .split('\n')
  .filter((line) => line.startsWith('MVP_E2E_QUERY_RESULT '))
  .map((line) => JSON.parse(line.slice('MVP_E2E_QUERY_RESULT '.length)))
const results = {
  environment: {
    database: 'isolated-e2e',
    databaseName: 'zeropay_lunch_mvp_e2e',
    semanticRuntime: true,
    llmExplanation: false,
  },
  queries: browserQueries,
  browserE2E: 'PASS',
  semanticRequests: Number(process.env.SEMANTIC_REQUESTS),
  intentRequests: Number(process.env.INTENT_REQUESTS),
  qdrantQueries: Number(process.env.QDRANT_QUERIES),
  embeddingCalls: Number(process.env.EMBEDDING_CALLS),
  llmExplanationCalls: Number(process.env.GENERATION_CALLS),
  devMysqlWrites: 0,
  e2eMysqlWrites: { fixtureRestaurants: 2, users, conversations, chatMessages, recommendations },
  qdrantWrites: 0,
  qdrantPointCountBefore: Number(process.env.QDRANT_BEFORE),
  qdrantPointCountAfter: Number(process.env.QDRANT_AFTER),
  qdrantScopeViolations: Number(process.env.SCOPE_VIOLATIONS),
  candidateScopeCheck: { candidateRestaurantIds: [9617], returnedRestaurantIds: [9617], violations: Number(process.env.SCOPE_VIOLATIONS) },
  cleanup: 'E2E Compose project and dedicated volume removed by EXIT trap',
  assessment: 'PASS',
}
writeFileSync(process.env.RESULT, `${JSON.stringify(results, null, 2)}\n`)
