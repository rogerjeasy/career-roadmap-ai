Here are the architecture design of my application: Directory:
  C:\Users\User\Documents\career-roadmap-ai\documentation\architecture-design


  Mode                 LastWriteTime         Length Name
  ----                 -------------         ------ ----
  -a----         4/29/2026   6:11 PM          60728 career-roadmap-agentic-backend-architecture.html
  -a----          5/1/2026  12:30 PM          40781 career-roadmap-architecture(1).html and the project description is
  located in Directory: C:\Users\User\Documents\career-roadmap-ai\documentation\documents


  Mode                 LastWriteTime         Length Name
  ----                 -------------         ------ ----
  -a----         4/29/2026   1:14 PM          38528 career-roadmap-ai-merged.docx. I have already implemented L2 AI Orchestr. CORE and part of L3 Specialist Agents WORKERS, i.e 🎙 Intake & Profile Agent, CV Analysis Agent, Gap Analysis Agent. Now I want to start working on: 
  
📈 Progress & Adaptation Agent
Reads weekly scorecard logs
Detects drift from plan
Proposes plan adaptations
Habit streak analysis
Re-triggers generation if needed
adapt
analytics

You should first start by understanding the architecture design documents and the project description file to have a clear idea of the implementation levels.
After, Provide the implementation using software best practicies like low coupling, high decoupling.
Always add observability and monitoring tools


great, now write a markdown document about it in the folder \documentation\implementation_summaries. Keep it short and concise


-------------------- THINGS IMPORTANT TO CONSIDER -------------------
1. Governance dashboard: real-time monitoring tools should be integrated to visualize AI decisions, flag anomalies, and track bias metrics.
2. Bias mitigation strategies: the architecture must incorporate measurable mechanisms to identify and mitigate bias in both training data and model outputs.
3. Auditability components: Logging mechanisms must record model decisions, inference data, and responses in a manner that allows for retrospective review and validation.
4. Confidence scoring: AI responses should include confidence metrics to indicate reliability, requiring specific measurement components in the architecture.
5. Decision tracing: The architecture should enable logging of intermediate steps in AI pipelines, allowing for retrospective analysis and debugging of model behavior.
6. Automated compliance testing: incorporate validation mechanisms that periodically test AI decisions against compliance standards.
7. Change control: be able to execute rollbacks, failovers, and decision management, such as when to disable non-deterministic decision-making.

------------------------------------------------

can you generate a skill or instruction (s) markdown file(s) about the entire project pattern that you will put in .claude folder such that it will be loaded at the start of every conversation, instead of the model to be going through the entire large codebase.

It should also provide or go to the following in order for the model to know the architecture design and project description: Directory:
  C:\Users\User\Documents\career-roadmap-ai\documentation\architecture-design


  Mode                 LastWriteTime         Length Name
  ----                 -------------         ------ ----
  -a----         4/29/2026   6:11 PM          60728 career-roadmap-agentic-backend-architecture.html
  -a----          5/1/2026  12:30 PM          40781 career-roadmap-architecture(1).html and the project description is
  located in Directory: C:\Users\User\Documents\career-roadmap-ai\documentation\documents


  Mode                 LastWriteTime         Length Name
  ----                 -------------         ------ ----
  -a----         4/29/2026   1:14 PM          38528 career-roadmap-ai-merged.docx.

Also as part those instructions, it should also contain, the use of software best practicies like low coupling, high decoupling. Always add observability and monitoring tools
Also add the following: 
15. Security, privacy, and responsible AI
The system handles CVs, career goals, progress history, and connected accounts. Security must be designed into every layer, especially agent tools and generated decisions.

Security controls
JWT access tokens, refresh tokens in HttpOnly Secure SameSite cookies.
Per-user row-level isolation in repositories and service methods.
Encryption at rest for uploaded documents and sensitive fields.
Tool-call audit logs for MCP actions.
Rate limiting on auth, chat, generation, and tool endpoints.
Secrets managed outside code through environment or secret manager.

Responsible AI controls
Do not infer protected attributes or reduce ambition based on them.
Expose uncertainty and assumptions to users.
Allow users to delete documents and derived analyses.
Require consent for external account connections.
Keep a human approval gate for write actions and critical plan changes.
Provide explanations for important recommendations.

----------
Here are the architecture design of my application: Directory:
  C:\Users\User\Documents\career-roadmap-ai\documentation\architecture-design


  Mode                 LastWriteTime         Length Name
  ----                 -------------         ------ ----
  -a----         4/29/2026   6:11 PM          60728 career-roadmap-agentic-backend-architecture.html
  -a----          5/1/2026  12:30 PM          40781 career-roadmap-architecture(1).html and the project description is
  located in Directory: C:\Users\User\Documents\career-roadmap-ai\documentation\documents


  Mode                 LastWriteTime         Length Name
  ----                 -------------         ------ ----
  -a----         4/29/2026   1:14 PM          38528 career-roadmap-ai-merged.docx.

Now I want to start working on L4
MCP
Servers
TOOLS: 
mcp_call(job_board)
rag_retrieve(career_kb)
mcp_call(course_search)
mcp_call(github_trends)
mcp_call(salary_bench)

MCP Tool Server Registry — agents compose at runtime via JSON-RPC 2.0, permission-scoped & user-revocable
MCP protocol: All servers expose JSON-RPC 2.0 via stdio or HTTP transport. The agent runtime maintains a tool registry — agents call mcp.call(server_id, tool, params). Runtime resolves, authenticates, rate-limits, and proxies. All integrations are permission-based, transparent, and user-revocable.

I will start with the following: 

🗄 Vector Store
Pinecone 
Namespaces per knowledge type
Hybrid: dense + sparse (BM25)
Metadata filtering
~1M+ career knowledge chunks

You should first start by understanding the architecture design documents and the project description file to have a clear idea of the implementation levels.
After, Provide the implementation using software best practicies like low coupling, high decoupling.
Always add observability and monitoring tools


📝 Context Injector
Builds agent prompt context
Inserts retrieved passages
Source citations attached
Token budget management
Anti-hallucination grounding

Anti-hallucination: Every roadmap step must cite a RAG chunk OR verified MCP data point. Output Validator checks this — uncited claims are flagged and either grounded or removed before delivery.

Hallucination prevention and realism controls
The system must make it difficult for unsupported claims to survive. Validation is done before the user sees a final roadmap and again before persistence.

Guardrail
No source, no claim
Company hiring claims, salary ranges, trending skills, visa guidance, certification value, course metadata, and local event recommendations must reference evidence cards or be labelled as assumptions.

Guardrail
Timeline feasibility scoring
The validator checks milestone volume against weekly hours, current skill level, target difficulty, and user constraints. Unrealistic plans are returned for repair.

Guardrail
Contradiction detection
The validator compares user statements, CV evidence, prior preferences, and generated plan. Contradictions trigger clarification or a visible warning.

Guardrail
Freshness policy
Market-sensitive data must include retrieved_at and source_date. Stale market signals are downgraded or excluded from high-impact recommendations.

Guardrail
Uncertainty display
Recommendations include confidence labels: high, medium, low. Low-confidence recommendations require explanation and optional user confirmation.

Guardrail
Schema validation
All LLM output is parsed into Pydantic schemas. Invalid output is rejected, repaired, and logged. Free-form text is never directly persisted as roadmap state.

Now check all the config files to see if all variable there are in my career-roadmap-ai\apps\api>.env file if there are missing variables, you should added them in the .env file. And please make sure no variable is or are hard coded in codes or implementations.

Now I want to start working on the frontend side of the career roadmap ai application with the technology:
Next.js 16 App
React TypeScript · App Router
Tailwind CSS · shadcn/ui · Zustand
TanStack Query · Zod
WebSocket
REST
SSE
I want you to update the CLAUDE.md file and also create the frontend-patterns.md in the .claude folder. 
As for pattern you should me use of the very best practices of a world class expert software engineer, allow maintenaibility for long term, reusability, the DRY principle. 

I have the following mockup html file
  file:///C:/Users/User/Documents/career-roadmap-ai/documentation/ui-mockup/03_onboarding.html for the career roadmap ai
   application, I want to start implemented that, I already have the login and register pages implemented. YOU SHOULD
  ALWAYS BREAK LARGE COMPONENTS TO SUBCOMPONENTS. AND MAKE USE OF THE BACKEND API ENDPOINTS THAT WERE ALREADY
  IMPLEMENTED. I ALSO HAVE A KONG API GATEWAY LAYER
The user upload their CV/resume, the hit a button that will send a request to the the backend api in order to extract most valuable information like for example: Found
5 roles
across
7 years
of experience
Detected
34 skills
· 12 strong, 22 supporting
Identified
4 standout projects
and
2 leadership signals
Education in
Computer Science · ETH Zürich, 2017 like shown in the mockup, but coming from the backend.


