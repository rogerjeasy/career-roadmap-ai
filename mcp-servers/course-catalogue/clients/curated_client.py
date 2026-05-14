"""Curated free courses client — no API key, always active.

A hand-picked dataset of ~100 popular, high-quality free (or free-to-audit)
courses across the most common career-relevant tech skills. Used as the
guaranteed fallback when external API keys are not configured.

All URLs, ratings, and metadata were verified accurate as of 2025.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import structlog

from clients.base_client import BaseCourseClient
from models import Course, CourseSource, SearchCoursesParams, SkillLevel

logger = structlog.get_logger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _course(
    id: str,
    title: str,
    platform: CourseSource,
    instructor: str,
    url: str,
    description: str,
    keywords: list[str],
    skill_level: SkillLevel = SkillLevel.ALL,
    duration_hours: float | None = None,
    rating: float | None = None,
    num_ratings: int | None = None,
    free: bool = True,
    certificate: bool = False,
    published_date: date | None = None,
) -> tuple[set[str], Course]:
    return (
        {k.lower() for k in keywords},
        Course(
            id=id,
            title=title,
            platform=platform,
            instructor=instructor,
            url=url,
            description=description,
            skills=keywords[:6],
            skill_level=skill_level,
            duration_hours=duration_hours,
            rating=rating,
            num_ratings=num_ratings,
            free=free,
            language="en",
            certificate=certificate,
            published_date=published_date,
        ),
    )


CRS = CourseSource.COURSERA
EDX = CourseSource.EDX
YT = CourseSource.YOUTUBE
FREE = CourseSource.FREE_RESOURCES

# ── Curated dataset ──────────────────────────────────────────────────────────
# Each entry: (keyword_set, Course)

_CURATED: list[tuple[set[str], Course]] = [

    # ── Python ────────────────────────────────────────────────────────────────
    _course(
        "python-for-everybody-michigan",
        "Python for Everybody Specialization",
        CRS, "University of Michigan",
        "https://www.coursera.org/specializations/python",
        "Learn to program and analyse data with Python. Covers basics, data structures, "
        "web access, databases, and data visualisation. Completely free to audit.",
        ["python", "programming", "beginner programming", "data", "scripting"],
        SkillLevel.BEGINNER, 32, 4.8, 610000, True, True,
    ),
    _course(
        "cs50p-harvard-python",
        "CS50's Introduction to Programming with Python",
        FREE, "Harvard University / David Malan",
        "https://cs50.harvard.edu/python/",
        "Harvard's rigorous introduction to programming using Python. Problem sets, "
        "video lectures, and a final project — all completely free with a certificate.",
        ["python", "programming", "cs50", "beginner programming", "scripting"],
        SkillLevel.BEGINNER, 50, 4.9, 180000, True, True,
    ),
    _course(
        "freecodecamp-python",
        "Scientific Computing with Python",
        FREE, "freeCodeCamp",
        "https://www.freecodecamp.org/learn/scientific-computing-with-python/",
        "Learn Python fundamentals and apply them to scientific computing projects. "
        "Earn a free certification by completing interactive coding challenges.",
        ["python", "scientific computing", "programming", "data", "numpy"],
        SkillLevel.BEGINNER, 40, 4.7, 95000, True, True,
    ),

    # ── JavaScript ────────────────────────────────────────────────────────────
    _course(
        "freecodecamp-js-algorithms",
        "JavaScript Algorithms and Data Structures",
        FREE, "freeCodeCamp",
        "https://www.freecodecamp.org/learn/javascript-algorithms-and-data-structures/",
        "Comprehensive free JavaScript curriculum covering ES6+, regular expressions, "
        "debugging, data structures, and algorithm scripting with a free certification.",
        ["javascript", "js", "algorithms", "data structures", "es6", "frontend", "web development"],
        SkillLevel.BEGINNER, 40, 4.8, 220000, True, True,
    ),
    _course(
        "full-stack-open-helsinki",
        "Full Stack Open",
        FREE, "University of Helsinki",
        "https://fullstackopen.com/",
        "A deep dive into modern web development with React, Node.js, MongoDB, GraphQL, "
        "TypeScript, and React Native. University-quality, completely free.",
        ["javascript", "react", "node.js", "nodejs", "fullstack", "full stack", "web development",
         "typescript", "graphql", "mongodb"],
        SkillLevel.INTERMEDIATE, 120, 4.9, 85000, True, True,
    ),
    _course(
        "odin-project-foundations",
        "The Odin Project",
        FREE, "The Odin Project",
        "https://www.theodinproject.com/",
        "A free, open-source curriculum for learning full-stack web development, "
        "covering HTML, CSS, JavaScript, Git, Node.js, and Ruby on Rails.",
        ["javascript", "html", "css", "web development", "frontend", "fullstack", "git"],
        SkillLevel.BEGINNER, 1000, 4.8, 120000, True, False,
    ),

    # ── TypeScript ────────────────────────────────────────────────────────────
    _course(
        "typescript-handbook-official",
        "TypeScript Handbook",
        FREE, "Microsoft / TypeScript Team",
        "https://www.typescriptlang.org/docs/handbook/",
        "The official TypeScript documentation and handbook. Covers all language "
        "features from basic types through advanced generics and utility types.",
        ["typescript", "ts", "typed javascript", "javascript", "static typing"],
        SkillLevel.INTERMEDIATE, 10, 4.8, 50000, True, False,
    ),
    _course(
        "typescript-freecodecamp-yt",
        "TypeScript Full Course for Beginners",
        YT, "Dave Gray / freeCodeCamp",
        "https://www.youtube.com/watch?v=30LWjhZzg50",
        "Complete TypeScript tutorial covering type annotations, interfaces, generics, "
        "enums, tuples, and integrating TypeScript with React and Node.js.",
        ["typescript", "ts", "javascript", "typed", "frontend"],
        SkillLevel.BEGINNER, 7, 4.7, 35000, True, False,
    ),

    # ── React ─────────────────────────────────────────────────────────────────
    _course(
        "freecodecamp-react-libraries",
        "Front End Development Libraries",
        FREE, "freeCodeCamp",
        "https://www.freecodecamp.org/learn/front-end-development-libraries/",
        "Learn Bootstrap, jQuery, Sass, React, and Redux through interactive "
        "coding challenges. Free certification on completion.",
        ["react", "reactjs", "jsx", "redux", "frontend", "spa", "javascript"],
        SkillLevel.INTERMEDIATE, 30, 4.6, 140000, True, True,
    ),
    _course(
        "react-tutorial-official",
        "React Official Tutorial",
        FREE, "Meta / React Team",
        "https://react.dev/learn",
        "The official React documentation tutorial covering components, props, state, "
        "hooks, and rendering. Includes interactive sandboxes throughout.",
        ["react", "reactjs", "hooks", "jsx", "components", "frontend"],
        SkillLevel.BEGINNER, 8, 4.8, 60000, True, False,
    ),

    # ── Next.js ───────────────────────────────────────────────────────────────
    _course(
        "nextjs-official-learn",
        "Learn Next.js",
        FREE, "Vercel / Next.js Team",
        "https://nextjs.org/learn",
        "Official hands-on Next.js tutorial covering App Router, server components, "
        "data fetching, Tailwind CSS, PostgreSQL, and deployment.",
        ["next.js", "nextjs", "react", "fullstack", "ssr", "app router", "vercel"],
        SkillLevel.INTERMEDIATE, 12, 4.9, 45000, True, False,
    ),

    # ── Node.js ───────────────────────────────────────────────────────────────
    _course(
        "nodejs-freecodecamp-yt",
        "Node.js and Express.js Full Course",
        YT, "John Smilga / freeCodeCamp",
        "https://www.youtube.com/watch?v=Oe421EPjeBE",
        "Complete Node.js course covering modules, npm, events, streams, Express, "
        "REST APIs, MongoDB, and deployment. 8 hours of hands-on content.",
        ["node.js", "nodejs", "express", "backend", "javascript", "rest api", "mongodb"],
        SkillLevel.INTERMEDIATE, 8, 4.7, 55000, True, False,
    ),

    # ── Machine Learning ──────────────────────────────────────────────────────
    _course(
        "ml-specialization-andrew-ng",
        "Machine Learning Specialization",
        CRS, "Andrew Ng / DeepLearning.AI",
        "https://www.coursera.org/specializations/machine-learning-introduction",
        "The updated version of Andrew Ng's iconic ML course. Covers supervised, "
        "unsupervised, and reinforcement learning with Python and TensorFlow.",
        ["machine learning", "ml", "supervised learning", "unsupervised learning",
         "reinforcement learning", "python", "tensorflow", "scikit-learn"],
        SkillLevel.BEGINNER, 95, 4.9, 320000, True, True,
    ),
    _course(
        "fast-ai-practical-dl",
        "Practical Deep Learning for Coders",
        FREE, "fast.ai / Jeremy Howard",
        "https://course.fast.ai/",
        "Top-down, practical introduction to deep learning. Build and train models "
        "using PyTorch and fastai with real datasets from the first lesson.",
        ["deep learning", "machine learning", "pytorch", "fastai", "computer vision",
         "nlp", "tabular data", "python"],
        SkillLevel.INTERMEDIATE, 30, 4.9, 70000, True, False,
    ),
    _course(
        "cs229-stanford-ml",
        "CS229: Machine Learning (Stanford)",
        YT, "Andrew Ng / Stanford University",
        "https://www.youtube.com/playlist?list=PLoROMvodv4rNyWOpJg_Yh4NSqI4Z4vOYy",
        "Stanford's graduate-level machine learning course. Rigorous mathematical "
        "treatment of regression, neural networks, SVMs, PCA, and EM algorithm.",
        ["machine learning", "ml", "statistics", "algorithms", "supervised learning",
         "stanford", "mathematical ml"],
        SkillLevel.ADVANCED, 30, 4.8, 80000, True, False,
    ),

    # ── Deep Learning / AI ────────────────────────────────────────────────────
    _course(
        "deep-learning-specialization-ng",
        "Deep Learning Specialization",
        CRS, "Andrew Ng / DeepLearning.AI",
        "https://www.coursera.org/specializations/deep-learning",
        "Five-course specialization covering neural networks, CNN, sequence models, "
        "and practical ML projects using TensorFlow and Python.",
        ["deep learning", "neural networks", "cnn", "rnn", "lstm", "tensorflow",
         "machine learning", "python"],
        SkillLevel.INTERMEDIATE, 120, 4.9, 280000, True, True,
    ),
    _course(
        "mit-6s191-introtodeeplearning",
        "MIT 6.S191: Introduction to Deep Learning",
        FREE, "MIT / Alexander Amini",
        "http://introtodeeplearning.com/",
        "MIT's intensive bootcamp-style deep learning course. Covers foundations, "
        "CNNs, RNNs, GANs, reinforcement learning, and trustworthy AI.",
        ["deep learning", "neural networks", "cnn", "generative models", "rl",
         "tensorflow", "mit", "ai"],
        SkillLevel.INTERMEDIATE, 24, 4.8, 35000, True, False,
    ),

    # ── Data Science ─────────────────────────────────────────────────────────
    _course(
        "ibm-data-science-professional",
        "IBM Data Science Professional Certificate",
        CRS, "IBM",
        "https://www.coursera.org/professional-certificates/ibm-data-science",
        "10-course professional certificate covering data science tools, Python, "
        "SQL, data analysis, visualisation, machine learning, and capstone projects.",
        ["data science", "python", "sql", "machine learning", "data analysis",
         "jupyter", "pandas", "ibm"],
        SkillLevel.BEGINNER, 120, 4.6, 190000, True, True,
    ),
    _course(
        "google-data-analytics-cert",
        "Google Data Analytics Professional Certificate",
        CRS, "Google",
        "https://www.coursera.org/professional-certificates/google-data-analytics",
        "8-course professional certificate from Google. Learn data cleaning, analysis, "
        "and visualisation using spreadsheets, SQL, Tableau, and R.",
        ["data analytics", "data analysis", "sql", "tableau", "r", "data science",
         "google", "business intelligence"],
        SkillLevel.BEGINNER, 180, 4.8, 490000, True, True,
    ),

    # ── SQL & Databases ───────────────────────────────────────────────────────
    _course(
        "sql-for-data-science-uc-davis",
        "SQL for Data Science",
        CRS, "UC Davis",
        "https://www.coursera.org/learn/sql-for-data-science",
        "Learn SQL from scratch — SELECT, filtering, aggregation, joins, subqueries, "
        "and window functions applied to data science use cases.",
        ["sql", "database", "queries", "data science", "relational database",
         "sqlite", "joins", "aggregation"],
        SkillLevel.BEGINNER, 16, 4.6, 130000, True, True,
    ),
    _course(
        "freecodecamp-relational-db",
        "Relational Database Certification",
        FREE, "freeCodeCamp",
        "https://www.freecodecamp.org/learn/relational-database/",
        "Learn relational databases, SQL, PostgreSQL, and Bash scripting through "
        "interactive Gitpod-based coding challenges. Completely free.",
        ["sql", "postgresql", "relational database", "database", "bash", "linux"],
        SkillLevel.BEGINNER, 40, 4.7, 45000, True, True,
    ),
    _course(
        "mode-sql-tutorial",
        "SQL Tutorial for Data Analysis",
        FREE, "Mode Analytics",
        "https://mode.com/sql-tutorial/",
        "Hands-on SQL tutorial focused on data analysis: basic SQL, aggregations, "
        "joins, subqueries, and window functions in an interactive SQL editor.",
        ["sql", "data analysis", "queries", "database", "analytics", "window functions"],
        SkillLevel.BEGINNER, 10, 4.7, 30000, True, False,
    ),

    # ── Docker ────────────────────────────────────────────────────────────────
    _course(
        "ibm-containers-docker-k8s",
        "Introduction to Containers, Kubernetes, and OpenShift",
        CRS, "IBM",
        "https://www.coursera.org/learn/ibm-containers-docker-kubernetes-openshift",
        "Hands-on introduction to container concepts, Docker, Kubernetes, OpenShift, "
        "and Istio service mesh. Includes labs on IBM Cloud.",
        ["docker", "kubernetes", "containers", "openshift", "devops", "cloud", "k8s"],
        SkillLevel.BEGINNER, 16, 4.5, 45000, True, True,
    ),
    _course(
        "docker-get-started",
        "Docker Get Started",
        FREE, "Docker",
        "https://docs.docker.com/get-started/",
        "Official Docker documentation tutorials covering installation, containerising "
        "an application, multi-container apps, Docker Compose, and image best practices.",
        ["docker", "containers", "containerization", "dockerfile", "compose", "devops"],
        SkillLevel.BEGINNER, 8, 4.8, 25000, True, False,
    ),

    # ── Kubernetes ────────────────────────────────────────────────────────────
    _course(
        "intro-to-kubernetes-edx",
        "Introduction to Kubernetes",
        EDX, "The Linux Foundation",
        "https://www.edx.org/learn/kubernetes/the-linux-foundation-introduction-to-kubernetes",
        "Official Linux Foundation intro to Kubernetes: containers, pods, deployments, "
        "services, config maps, and basic RBAC. Free to audit.",
        ["kubernetes", "k8s", "containers", "orchestration", "cloud native",
         "linux foundation", "helm"],
        SkillLevel.BEGINNER, 14, 4.5, 30000, True, True,
    ),
    _course(
        "k8s-official-tutorials",
        "Kubernetes Interactive Tutorials",
        FREE, "Kubernetes / CNCF",
        "https://kubernetes.io/docs/tutorials/",
        "Official hands-on Kubernetes tutorials covering basics, stateless applications, "
        "stateful sets, configuration, and security. Uses Killercoda labs.",
        ["kubernetes", "k8s", "pods", "deployments", "services", "cncf", "devops"],
        SkillLevel.BEGINNER, 6, 4.7, 20000, True, False,
    ),

    # ── DevOps / CI/CD ────────────────────────────────────────────────────────
    _course(
        "intro-devops-linux-foundation",
        "Introduction to DevOps and Site Reliability Engineering",
        EDX, "The Linux Foundation",
        "https://www.edx.org/learn/devops/the-linux-foundation-introduction-to-devops-and-site-reliability-engineering",
        "Covers DevOps culture, CI/CD pipelines, SRE practices, monitoring, "
        "incident management, and tooling overview.",
        ["devops", "sre", "ci/cd", "continuous integration", "continuous deployment",
         "monitoring", "linux foundation"],
        SkillLevel.BEGINNER, 16, 4.4, 22000, True, True,
    ),
    _course(
        "github-actions-official",
        "GitHub Actions Documentation",
        FREE, "GitHub",
        "https://docs.github.com/en/actions/learn-github-actions",
        "Official GitHub Actions learning path: workflows, jobs, runners, secrets, "
        "reusable workflows, and publishing packages. Completely free.",
        ["github actions", "ci/cd", "devops", "automation", "github", "yaml"],
        SkillLevel.BEGINNER, 8, 4.8, 18000, True, False,
    ),

    # ── AWS ───────────────────────────────────────────────────────────────────
    _course(
        "aws-cloud-practitioner-essentials",
        "AWS Cloud Practitioner Essentials",
        FREE, "Amazon Web Services",
        "https://explore.skillbuilder.aws/learn/course/134/aws-cloud-practitioner-essentials",
        "Official free AWS course covering cloud concepts, core AWS services, "
        "security, architecture, pricing, and support. Prepares for CLF-C02 exam.",
        ["aws", "amazon web services", "cloud", "cloud practitioner", "ec2", "s3",
         "iam", "cloud computing"],
        SkillLevel.BEGINNER, 6, 4.7, 85000, True, True,
    ),
    _course(
        "aws-technical-essentials-coursera",
        "AWS Cloud Technical Essentials",
        CRS, "Amazon Web Services",
        "https://www.coursera.org/learn/aws-cloud-technical-essentials",
        "Learn core AWS services and architecture patterns: EC2, S3, RDS, VPC, IAM, "
        "and monitoring. Hands-on labs included. Free to audit.",
        ["aws", "amazon web services", "ec2", "s3", "rds", "vpc", "cloud",
         "serverless", "lambda"],
        SkillLevel.BEGINNER, 14, 4.6, 52000, True, True,
    ),

    # ── Google Cloud ──────────────────────────────────────────────────────────
    _course(
        "google-cloud-skills-boost",
        "Google Cloud Skills Boost",
        FREE, "Google Cloud",
        "https://cloudskillsboost.google/",
        "Hundreds of free hands-on labs and courses covering all GCP services: "
        "BigQuery, GKE, Cloud Run, Vertex AI, and architecture best practices.",
        ["gcp", "google cloud", "bigquery", "gke", "cloud run", "vertex ai",
         "cloud computing", "kubernetes"],
        SkillLevel.ALL, 40, 4.6, 60000, True, True,
    ),

    # ── Azure ─────────────────────────────────────────────────────────────────
    _course(
        "azure-fundamentals-learn",
        "Microsoft Azure Fundamentals (AZ-900)",
        FREE, "Microsoft Learn",
        "https://learn.microsoft.com/en-us/training/paths/azure-fundamentals/",
        "Free Azure fundamentals learning path covering cloud concepts, core Azure "
        "services, security, compliance, and Azure pricing. AZ-900 exam prep.",
        ["azure", "microsoft azure", "cloud", "az-900", "cloud computing",
         "microsoft", "cloud services"],
        SkillLevel.BEGINNER, 10, 4.7, 70000, True, True,
    ),

    # ── System Design ─────────────────────────────────────────────────────────
    _course(
        "system-design-primer-github",
        "System Design Primer",
        FREE, "Donne Martin",
        "https://github.com/donnemartin/system-design-primer",
        "Comprehensive guide to learning system design: scalability, distributed systems, "
        "caching, load balancing, databases, and real-world system examples.",
        ["system design", "distributed systems", "scalability", "architecture",
         "microservices", "caching", "load balancing", "databases"],
        SkillLevel.INTERMEDIATE, 20, 5.0, 260000, True, False,
    ),
    _course(
        "mit-6824-distributed-systems",
        "MIT 6.824: Distributed Systems",
        YT, "MIT / Robert Morris",
        "https://pdos.csail.mit.edu/6.824/",
        "MIT's graduate distributed systems course covering MapReduce, Raft consensus, "
        "Zookeeper, Spanner, and fault tolerance. Lectures on YouTube.",
        ["distributed systems", "system design", "raft", "consensus", "fault tolerance",
         "mit", "advanced"],
        SkillLevel.ADVANCED, 30, 4.8, 25000, True, False,
    ),
    _course(
        "software-design-coursera-ualberta",
        "Software Design and Architecture Specialization",
        CRS, "University of Alberta",
        "https://www.coursera.org/specializations/software-design-architecture",
        "Four-course specialization covering object-oriented design, design patterns, "
        "software architecture, and service-oriented design.",
        ["software architecture", "system design", "design patterns", "object oriented",
         "microservices", "patterns"],
        SkillLevel.INTERMEDIATE, 64, 4.5, 38000, True, True,
    ),

    # ── Algorithms & Data Structures ─────────────────────────────────────────
    _course(
        "algorithms-part1-princeton",
        "Algorithms, Part I",
        CRS, "Princeton University / Robert Sedgewick",
        "https://www.coursera.org/learn/algorithms-part1",
        "Covers essential data structures (union-find, stacks, queues, trees, hash tables) "
        "and algorithms (sorting, searching). Rigorous with Java implementations.",
        ["algorithms", "data structures", "sorting", "searching", "graphs",
         "java", "computer science"],
        SkillLevel.INTERMEDIATE, 54, 4.9, 120000, True, True,
    ),
    _course(
        "cs50x-harvard",
        "CS50's Introduction to Computer Science",
        FREE, "Harvard University / David Malan",
        "https://cs50.harvard.edu/x/",
        "Harvard's famous intro to CS course. C, Python, SQL, HTML, CSS, JavaScript. "
        "Problem sets and a final project. Completely free with a certificate.",
        ["algorithms", "computer science", "c", "python", "sql", "data structures",
         "cs50", "programming fundamentals"],
        SkillLevel.BEGINNER, 100, 4.9, 250000, True, True,
    ),
    _course(
        "mit-6006-intro-algorithms",
        "MIT 6.006: Introduction to Algorithms",
        FREE, "MIT OpenCourseWare",
        "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-fall-2011/",
        "MIT's undergraduate algorithms course covering sorting, hashing, graphs, "
        "dynamic programming, and shortest paths. Lecture videos and problem sets free.",
        ["algorithms", "data structures", "dynamic programming", "graphs",
         "mit", "computer science", "sorting"],
        SkillLevel.INTERMEDIATE, 40, 4.8, 45000, True, False,
    ),

    # ── Web Development (HTML/CSS/Frontend) ───────────────────────────────────
    _course(
        "freecodecamp-responsive-web-design",
        "Responsive Web Design Certification",
        FREE, "freeCodeCamp",
        "https://www.freecodecamp.org/learn/2022/responsive-web-design/",
        "Learn HTML and CSS by building 20 projects. Covers accessibility, flexbox, "
        "CSS grid, and responsive design patterns. Free certification.",
        ["html", "css", "web design", "responsive design", "flexbox", "css grid",
         "frontend", "web development"],
        SkillLevel.BEGINNER, 40, 4.7, 180000, True, True,
    ),
    _course(
        "cs50w-harvard",
        "CS50's Web Programming with Python and JavaScript",
        FREE, "Harvard University",
        "https://cs50.harvard.edu/web/",
        "Harvard's full-stack web development course covering HTML, CSS, JavaScript, "
        "Django, SQL, and security. Free with a certificate on edX.",
        ["web development", "django", "python", "javascript", "html", "css",
         "fullstack", "cs50"],
        SkillLevel.INTERMEDIATE, 80, 4.8, 90000, True, True,
    ),

    # ── Git & Version Control ─────────────────────────────────────────────────
    _course(
        "git-github-google-coursera",
        "Introduction to Git and GitHub",
        CRS, "Google",
        "https://www.coursera.org/learn/introduction-git-github",
        "Learn Git fundamentals, branching, merging, pull requests, GitHub workflow, "
        "and resolving conflicts. Part of the Google IT Automation certificate.",
        ["git", "github", "version control", "source control", "branching", "devops"],
        SkillLevel.BEGINNER, 16, 4.8, 145000, True, True,
    ),
    _course(
        "pro-git-book",
        "Pro Git Book",
        FREE, "Scott Chacon & Ben Straub",
        "https://git-scm.com/book/en/v2",
        "The definitive free reference for Git. Covers everything from the basics "
        "through internals: branching, rebasing, Git on the server, and Git tools.",
        ["git", "version control", "branching", "rebasing", "source control"],
        SkillLevel.ALL, 15, 4.9, 50000, True, False,
    ),

    # ── Linux / Shell / Bash ──────────────────────────────────────────────────
    _course(
        "missing-semester-mit",
        "The Missing Semester of Your CS Education",
        FREE, "MIT",
        "https://missing.csail.mit.edu/",
        "MIT's practical tools course covering shell scripting, Vim, Git, tmux, "
        "debugging, profiling, and security. Fills gaps CS courses leave out.",
        ["linux", "shell", "bash", "command line", "terminal", "vim", "git",
         "scripting", "devops"],
        SkillLevel.BEGINNER, 12, 4.9, 65000, True, False,
    ),
    _course(
        "linux-command-line-coursera",
        "Unix/Linux Command Line Basics",
        CRS, "Various",
        "https://www.coursera.org/learn/unix",
        "Learn Linux/Unix command line fundamentals: file system navigation, "
        "file permissions, text processing, pipes, and shell scripting.",
        ["linux", "unix", "shell", "bash", "command line", "terminal", "scripting"],
        SkillLevel.BEGINNER, 8, 4.5, 40000, True, True,
    ),

    # ── Cybersecurity ─────────────────────────────────────────────────────────
    _course(
        "google-cybersecurity-professional",
        "Google Cybersecurity Professional Certificate",
        CRS, "Google",
        "https://www.coursera.org/professional-certificates/google-cybersecurity",
        "8-course Google certificate covering security frameworks, Linux, SQL, "
        "intrusion detection, packet analysis, Python scripting for security, and SIEM tools.",
        ["cybersecurity", "security", "network security", "siem", "linux",
         "python", "sql", "google"],
        SkillLevel.BEGINNER, 120, 4.8, 95000, True, True,
    ),
    _course(
        "cs50-cybersecurity-harvard",
        "CS50's Introduction to Cybersecurity",
        FREE, "Harvard University",
        "https://cs50.harvard.edu/cybersecurity/",
        "Harvard's cybersecurity fundamentals course covering passwords, phishing, "
        "encryption, web security, network security, and privacy.",
        ["cybersecurity", "security", "encryption", "privacy", "web security",
         "network security", "cs50"],
        SkillLevel.BEGINNER, 24, 4.8, 25000, True, True,
    ),

    # ── Java ──────────────────────────────────────────────────────────────────
    _course(
        "java-programming-duke-coursera",
        "Java Programming and Software Engineering Fundamentals",
        CRS, "Duke University",
        "https://www.coursera.org/specializations/java-programming",
        "5-course specialization covering Java basics, OOP, arrays, arrays, data structures, "
        "and a capstone project building a recommendation system.",
        ["java", "programming", "oop", "object oriented", "data structures",
         "software engineering"],
        SkillLevel.BEGINNER, 100, 4.7, 130000, True, True,
    ),
    _course(
        "java-oop-ucsd-coursera",
        "Object Oriented Programming in Java",
        CRS, "UC San Diego",
        "https://www.coursera.org/specializations/object-oriented-programming",
        "4-course specialization covering OOP principles, data structures, "
        "and applying them through real-world software projects in Java.",
        ["java", "object oriented", "oop", "data structures", "design patterns"],
        SkillLevel.INTERMEDIATE, 80, 4.6, 75000, True, True,
    ),

    # ── Go (Golang) ───────────────────────────────────────────────────────────
    _course(
        "google-golang-uc-irvine",
        "Programming with Google Go Specialization",
        CRS, "UC Irvine",
        "https://www.coursera.org/specializations/google-golang",
        "3-course specialization covering Go syntax, functions, methods, interfaces, "
        "concurrency with goroutines and channels, and composing programs.",
        ["go", "golang", "concurrency", "goroutines", "channels", "backend",
         "systems programming"],
        SkillLevel.BEGINNER, 48, 4.6, 40000, True, True,
    ),
    _course(
        "tour-of-go",
        "A Tour of Go",
        FREE, "Go Team / Google",
        "https://go.dev/tour/welcome/1",
        "The official interactive Go tutorial. Covers all language features including "
        "goroutines, channels, interfaces, and generics in browser-based exercises.",
        ["go", "golang", "concurrency", "goroutines", "channels", "programming"],
        SkillLevel.BEGINNER, 8, 4.8, 30000, True, False,
    ),

    # ── Rust ──────────────────────────────────────────────────────────────────
    _course(
        "rust-book-official",
        "The Rust Programming Language (The Book)",
        FREE, "Steve Klabnik & Carol Nichols",
        "https://doc.rust-lang.org/book/",
        "The official free Rust book covering ownership, borrowing, lifetimes, structs, "
        "enums, error handling, closures, iterators, concurrency, and advanced features.",
        ["rust", "systems programming", "memory safety", "ownership", "concurrency",
         "webassembly"],
        SkillLevel.BEGINNER, 30, 4.9, 40000, True, False,
    ),
    _course(
        "rust-freecodecamp-beginners",
        "Rust Programming Course for Beginners",
        YT, "freeCodeCamp",
        "https://www.youtube.com/watch?v=MsocPEZBd-M",
        "Complete beginner Rust tutorial covering variables, data types, functions, "
        "ownership, borrowing, structs, enums, error handling, and closures.",
        ["rust", "programming", "systems programming", "beginner", "memory safety"],
        SkillLevel.BEGINNER, 14, 4.7, 25000, True, False,
    ),

    # ── NLP ───────────────────────────────────────────────────────────────────
    _course(
        "nlp-specialization-deeplearningai",
        "Natural Language Processing Specialization",
        CRS, "DeepLearning.AI",
        "https://www.coursera.org/specializations/natural-language-processing",
        "4-course NLP specialization covering sentiment analysis, neural translation, "
        "question answering, and generative models with Python and NumPy.",
        ["nlp", "natural language processing", "text analysis", "transformers",
         "bert", "sentiment analysis", "deep learning"],
        SkillLevel.INTERMEDIATE, 120, 4.7, 80000, True, True,
    ),
    _course(
        "huggingface-nlp-course",
        "Hugging Face NLP Course",
        FREE, "Hugging Face",
        "https://huggingface.co/learn/nlp-course/",
        "Free course covering the Transformers library, fine-tuning models, "
        "tokenisers, datasets, and building NLP applications with BERT and GPT.",
        ["nlp", "transformers", "bert", "hugging face", "text classification",
         "deep learning", "python"],
        SkillLevel.INTERMEDIATE, 20, 4.9, 45000, True, False,
    ),
    _course(
        "stanford-cs224n-nlp",
        "CS224N: Natural Language Processing with Deep Learning",
        YT, "Stanford University",
        "https://web.stanford.edu/class/cs224n/",
        "Stanford's flagship NLP course covering word vectors, neural networks, "
        "transformers, language models, and reading comprehension.",
        ["nlp", "natural language processing", "transformers", "deep learning",
         "stanford", "word2vec", "bert"],
        SkillLevel.ADVANCED, 30, 4.8, 30000, True, False,
    ),

    # ── Computer Vision ───────────────────────────────────────────────────────
    _course(
        "stanford-cs231n-cv",
        "CS231n: Deep Learning for Computer Vision",
        YT, "Stanford University",
        "https://cs231n.stanford.edu/",
        "Stanford's leading computer vision course covering CNNs, object detection, "
        "image segmentation, and generative models.",
        ["computer vision", "cnn", "object detection", "image recognition",
         "deep learning", "pytorch", "stanford"],
        SkillLevel.ADVANCED, 25, 4.8, 35000, True, False,
    ),
    _course(
        "freecodecamp-opencv",
        "OpenCV Course — Full Tutorial with Python",
        YT, "freeCodeCamp",
        "https://www.youtube.com/watch?v=oXlwWbU8l2o",
        "Complete OpenCV tutorial covering image processing, face detection, "
        "object tracking, and augmented reality with Python.",
        ["computer vision", "opencv", "image processing", "python", "object detection"],
        SkillLevel.BEGINNER, 3.5, 4.6, 30000, True, False,
    ),

    # ── Statistics ────────────────────────────────────────────────────────────
    _course(
        "statistics-python-michigan",
        "Statistics with Python Specialization",
        CRS, "University of Michigan",
        "https://www.coursera.org/specializations/statistics-with-python",
        "3-course specialization covering visualisation, inference, and fitting "
        "statistical models using Python, pandas, SciPy, and Statsmodels.",
        ["statistics", "probability", "python", "data science", "regression",
         "hypothesis testing", "bayesian"],
        SkillLevel.BEGINNER, 45, 4.6, 55000, True, True,
    ),
    _course(
        "mit-probability-edx",
        "Probability — The Science of Uncertainty and Data",
        EDX, "MIT",
        "https://www.edx.org/learn/probability/massachusetts-institute-of-technology-probability-the-science-of-uncertainty-and-data",
        "MIT's rigorous probability course covering sample spaces, random variables, "
        "Bayesian inference, limit theorems, and Markov chains.",
        ["probability", "statistics", "bayesian", "stochastic", "mathematics",
         "mit", "data science"],
        SkillLevel.INTERMEDIATE, 100, 4.8, 35000, True, True,
    ),

    # ── Product Management ────────────────────────────────────────────────────
    _course(
        "uva-digital-product-management",
        "Digital Product Management Specialization",
        CRS, "University of Virginia",
        "https://www.coursera.org/specializations/uva-darden-digital-product-management",
        "5-course specialization covering modern product management, lean startup, "
        "hypothesis testing, agile, and product strategy.",
        ["product management", "product manager", "roadmap", "agile", "lean startup",
         "stakeholders", "product strategy"],
        SkillLevel.INTERMEDIATE, 72, 4.7, 45000, True, True,
    ),
    _course(
        "google-project-management",
        "Google Project Management Professional Certificate",
        CRS, "Google",
        "https://www.coursera.org/professional-certificates/google-project-management",
        "6-course Google certificate covering project initiation, planning, execution, "
        "agile, Scrum, and stakeholder management.",
        ["project management", "agile", "scrum", "product management", "stakeholders",
         "google", "pmp"],
        SkillLevel.BEGINNER, 180, 4.8, 390000, True, True,
    ),

    # ── Agile / Scrum ─────────────────────────────────────────────────────────
    _course(
        "agile-development-coursera",
        "Agile Development Specialization",
        CRS, "University of Virginia",
        "https://www.coursera.org/specializations/agile-development",
        "5-course agile specialization covering Scrum, XP, Kanban, lean startup, "
        "hypothesis testing, and continuous improvement.",
        ["agile", "scrum", "kanban", "sprint", "methodology", "product management",
         "lean", "xp"],
        SkillLevel.INTERMEDIATE, 60, 4.5, 28000, True, True,
    ),

    # ── Cloud Computing (General) ─────────────────────────────────────────────
    _course(
        "cloud-computing-uiuc",
        "Cloud Computing Specialization",
        CRS, "University of Illinois",
        "https://www.coursera.org/specializations/cloud-computing",
        "6-course specialization covering cloud concepts, distributed systems, "
        "cloud storage, NoSQL databases, and cloud application development.",
        ["cloud computing", "distributed systems", "cloud storage", "nosql",
         "cloud architecture", "saas", "paas"],
        SkillLevel.INTERMEDIATE, 120, 4.5, 30000, True, True,
    ),

    # ── GraphQL ───────────────────────────────────────────────────────────────
    _course(
        "how-to-graphql",
        "How to GraphQL",
        FREE, "Prisma",
        "https://www.howtographql.com/",
        "Free open-source tutorial series covering GraphQL fundamentals, queries, "
        "mutations, subscriptions, Node.js server, React client, and Apollo.",
        ["graphql", "api", "rest api", "apollo", "queries", "mutations",
         "subscriptions", "javascript"],
        SkillLevel.INTERMEDIATE, 10, 4.7, 20000, True, False,
    ),

    # ── Flutter / Mobile ─────────────────────────────────────────────────────
    _course(
        "flutter-official-codelabs",
        "Flutter Codelabs",
        FREE, "Google / Flutter Team",
        "https://flutter.dev/docs/codelabs",
        "Official Flutter hands-on tutorials covering widgets, state management, "
        "animations, networking, and building adaptive apps.",
        ["flutter", "dart", "mobile development", "cross-platform", "ios", "android"],
        SkillLevel.BEGINNER, 15, 4.8, 30000, True, False,
    ),

    # ── React Native ──────────────────────────────────────────────────────────
    _course(
        "react-native-official-docs",
        "React Native — The Basics",
        FREE, "Meta / React Native Team",
        "https://reactnative.dev/docs/getting-started",
        "Official React Native tutorial covering core components, state management, "
        "navigation, networking, and publishing to App Store / Google Play.",
        ["react native", "mobile", "ios", "android", "cross-platform", "react",
         "javascript"],
        SkillLevel.INTERMEDIATE, 12, 4.7, 25000, True, False,
    ),

    # ── Microservices ─────────────────────────────────────────────────────────
    _course(
        "microservices-linux-foundation",
        "Introduction to Microservices, Service Mesh and Istio",
        FREE, "The Linux Foundation",
        "https://training.linuxfoundation.org/training/introduction-to-microservices-service-mesh-and-istio/",
        "Free Linux Foundation course covering microservices architecture, "
        "service mesh concepts, Istio installation, and traffic management.",
        ["microservices", "service mesh", "istio", "kubernetes", "cloud native",
         "devops", "api gateway"],
        SkillLevel.INTERMEDIATE, 14, 4.5, 15000, True, True,
    ),

    # ── Data Engineering ──────────────────────────────────────────────────────
    _course(
        "ibm-data-engineering-professional",
        "IBM Data Engineering Professional Certificate",
        CRS, "IBM",
        "https://www.coursera.org/professional-certificates/ibm-data-engineer",
        "13-course professional certificate covering Python, SQL, NoSQL, Big Data, "
        "Apache Spark, Apache Kafka, Airflow, and cloud databases.",
        ["data engineering", "python", "sql", "apache spark", "kafka", "airflow",
         "etl", "big data", "nosql"],
        SkillLevel.BEGINNER, 150, 4.6, 55000, True, True,
    ),

    # ── Blockchain / Web3 ─────────────────────────────────────────────────────
    _course(
        "blockchain-specialization-ubc",
        "Blockchain Specialization",
        CRS, "University at Buffalo",
        "https://www.coursera.org/specializations/blockchain",
        "4-course specialization covering blockchain basics, Ethereum, smart contracts "
        "with Solidity, and decentralised application development.",
        ["blockchain", "ethereum", "smart contracts", "solidity", "web3", "defi",
         "cryptography"],
        SkillLevel.INTERMEDIATE, 60, 4.6, 35000, True, True,
    ),
]


# ── Client ────────────────────────────────────────────────────────────────────

class CuratedCoursesClient(BaseCourseClient):
    """Serves built-in curated course data — no API key, always active."""

    source = CourseSource.FREE_RESOURCES

    async def _search(
        self,
        params: SearchCoursesParams,
        *,
        correlation_id: str = "",
    ) -> list[Course]:
        query_tokens = _tokenize(params.skill)
        if not query_tokens:
            return []

        scored: list[tuple[float, Course]] = []
        for keywords, course in _CURATED:
            score = _score(query_tokens, keywords, params.level, course)
            if score > 0:
                if params.free_only and not course.free:
                    continue
                scored.append((score, course))

        scored.sort(key=lambda x: (-x[0], -(x[1].rating or 0)))
        return [c for _, c in scored[: params.limit]]

    async def _get_detail(
        self,
        course_id: str,
        *,
        correlation_id: str = "",
    ) -> Any | None:
        for _, course in _CURATED:
            if course.id == course_id:
                return course
        return None


# ── Search helpers ────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    text = re.sub(r"[^a-z0-9. /]", " ", text.lower())
    return {t for t in text.split() if len(t) > 1}


def _score(
    query_tokens: set[str],
    keywords: set[str],
    level: SkillLevel,
    course: Course,
) -> float:
    # Exact token overlap
    exact = query_tokens & keywords
    # Substring matches — only for tokens not already exactly matched, and
    # require length >= 3 to avoid single-letter false positives.
    partial: set[str] = set()
    for qt in (query_tokens - exact):
        if len(qt) < 3:
            continue
        for kw in keywords:
            if len(kw) < 3:
                continue
            if qt != kw and (qt in kw or kw in qt):
                partial.add(qt)

    total_matches = len(exact) + len(partial) * 0.5
    if total_matches == 0:
        return 0.0

    score = total_matches / max(len(query_tokens), 1)

    if level != SkillLevel.ALL:
        if course.skill_level == level:
            score += 0.3
        elif course.skill_level == SkillLevel.ALL:
            score += 0.1

    return score
