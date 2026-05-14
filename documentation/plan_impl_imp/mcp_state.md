All 9 MCP servers are implemented across mcp-servers/:

  #: 1
  Server: job-board
  Port: 3001
  Tools: search_jobs, get_job_detail, get_trending_roles
  Always-active (no key): AdzunaClient (when keys set) or SwissJobsClient (jobs.ch / jobup.ch)
  Optional keys: LINKEDIN_API_KEY, INDEED_API_KEY, GLASSDOOR_API_KEY, ADZUNA_APP_ID/ADZUNA_APP_KEY
  ────────────────────────────────────────
  #: 2
  Server: course-catalogue
  Port: 3002
  Tools: search_courses, get_course_detail
  Always-active (no key): Curated ~100 courses + Coursera public API
  Optional keys: COURSERA_API_KEY, UDEMY_API_KEY, YOUTUBE_API_KEY, OREILLY_API_KEY
  ────────────────────────────────────────
  #: 3
  Server: salary-benchmark
  Port: 3003
  Tools: get_salary_range
  Always-active (no key): Curated Swiss/EU/US salary dataset
  Optional keys: GLASSDOOR_API_KEY (RapidAPI)
  ────────────────────────────────────────
  #: 4
  Server: github-trends
  Port: 3004
  Tools: get_trending_repos, get_good_first_issues
  Always-active (no key): GitHub REST API (60 req/hr unauthenticated)
  Optional keys: GITHUB_TOKEN (raises limit to 5 000 req/hr)
  ────────────────────────────────────────
  #: 5
  Server: social-signals
  Port: 3005
  Tools: get_hackernews_signals, get_reddit_signals, get_twitter_signals, get_devto_signals, get_trending_topics
  Always-active (no key): HackerNews (Algolia), Reddit public JSON, Dev.to public API
  Optional keys: TWITTER_BEARER_TOKEN, REDDIT_CLIENT_ID/SECRET, DEVTO_API_KEY
  ────────────────────────────────────────
  #: 6
  Server: calendar
  Port: 3006
  Tools: create_event, create_weekly_tasks, list_upcoming, store_oauth_token
  Always-active (no key): Both providers always registered
  Optional keys: GOOGLE_OAUTH_CLIENT_ID/SECRET, MICROSOFT_OAUTH_CLIENT_ID/SECRET, CALENDAR_TOKEN_ENCRYPTION_KEY
  ────────────────────────────────────────
  #: 7
  Server: industry-news
  Port: 3007
  Tools: search_news, get_weekly_digest
  Always-active (no key): 10 curated RSS feeds (HN, Google AI Blog, MIT Tech Review, The Batch, Papers With Code,
  OpenAI,
    Anthropic, InfoQ ML, Swiss ICT, Towards Data Science)
  Optional keys: NEWSAPI_KEY (newsapi.org)
  ────────────────────────────────────────
  #: 8
  Server: linkedin-profile
  Port: 3008
  Tools: fetch_profile, normalize_job_title, suggest_connections
  Always-active (no key): normalize_job_title (in-process, no API)
  Optional keys: LINKEDIN_API_KEY (RapidAPI linkedin-data-api)
  ────────────────────────────────────────
  #: 9
  Server: document-store
  Port: 3009
  Tools: upload_document, get_document, list_documents, delete_document
  Always-active (no key): Local filesystem (BLOB_STORAGE_PROVIDER=local)
  Optional keys: AZURE_STORAGE_CONNECTION_STRING or AWS_ACCESS_KEY_ID/SECRET

  All nine are wired to the agent pipeline via MCP_*_URL env vars in apps/api/.env. When a URL is not set, the
  StubMCPClient is used automatically and responses are tagged source: "stub".