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


great, now write a markdown document about it in the folder \documentation\implementation_summaries


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

