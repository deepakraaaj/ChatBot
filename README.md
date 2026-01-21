# ⚡ LightningBot (Optimized AI Backend)

A ultra-high-performance **FastAPI** backend designed for lighting-fast response times. This is an optimized version of the facility operations assistant, leveraging **Elasticsearch** for scalable vector search, **Redis** for aggressive caching, and **Bulk APIs** for high-throughput ingestion.

## 🏗️ Architecture

The backend is structured as a graph of specialized agents optimized for speed:
*   **Graph Engine**: Stateful, cyclical reasoning using `LangGraph`.
*   **Vector Search (ES)**: Uses **Elasticsearch** for production-grade, distributed vector search.
*   **Lightning Cache**: **Redis** caching for vectors and LLM responses, reducing latency by up to 80% on repeat queries.
*   **High-Speed Ingestion**: Optimized with Elasticsearch Bulk APIs.

## ✨ Lightning Features

- **Connection Pooling**: Optimized ES and Redis clients for high concurrency.
- **Selective Field Fetching**: Only retrieves required data from the database to minimize JSON overhead.
- **Batch Processing**: Parallelizes embedding generation for document ingestion.

## 🚀 Running with Docker (Lightning Mode)

The easiest way to find and run this system is using Docker Compose. The project is named **LightningBot** for easy identification.

```bash
# Start all services (Backend, ES, Redis, MySQL, Dashboard)
docker compose up -d

# Verify running containers
docker ps --filter name=lightning_
```

| Service | Container Name | Port |
| :--- | :--- | :--- |
| **Backend API** | `lightning_backend` | `8000` |
| **Elasticsearch** | `lightning_es` | `9201` |
| **Redis Cache** | `lightning_redis` | `6380` |
| **Dashboard** | `lightning_dashboard` | `8501` |

## 🏗️ System Architecture

The following diagram illustrates the core components of the **LightningBot** system and how they interact:

```mermaid
graph TD
    User([User / Client]) <--> API[FastAPI Backend]
    
    subgraph "Core Backend"
        API <--> Graph[LangGraph Engine]
        Graph <--> Nodes{Specialized Nodes}
    end
    
    subgraph "Data & Search"
        Nodes <--> ES[(Elasticsearch)]
        Nodes <--> Redis[(Redis Cache)]
        Nodes <--> DB[(MySQL / SQL DB)]
    end
    
    subgraph "LLM Layer"
        Nodes <--> Router[LLM Router]
        Router <--> Groq[Groq API]
        Router <--> Gemini[Gemini API]
        Router <--> Local[Self-Hosted LLM]
    end

    classDef primary fill:#f9f,stroke:#333,stroke-width:2px;
    classDef storage fill:#82b1ff,stroke:#333,stroke-width:2px;
    classDef llm fill:#b2ff59,stroke:#333,stroke-width:2px;
    
    class ES,Redis,DB storage;
    class Groq,Gemini,Local llm;
```

## 🔄 Request-Response Flow

This sequence diagram shows how a user query is processed through the multi-agent graph with caching and vector search:

```mermaid
sequenceDiagram
    participant U as User
    participant A as API
    participant G as Graph Engine
    participant C as Redis Cache
    participant V as Vector Service (ES)
    participant L as LLM Provider

    U->>A: Send Message
    A->>G: Initialize Workflow State
    G->>C: Check Cache for Query/Embedding
    alt Cache Hit
        C-->>G: Return Cached Data
    else Cache Miss
        G->>V: Perform Semantic Search
        V-->>G: Return Context
        G->>C: Cache Vector/Result
    end
    G->>L: Request Reasoning (with Context)
    L-->>G: Return AI Response
    G->>A: Finalize Response
    A->>U: Return Response (Streaming/JSON)
```

## 📂 Project Structure
```
app/
├── api/        # FastAPI Routes
├── core/       # Optimized ES/Redis Clients
├── db/         # SQL Models
├── graph/      # Multi-Agent Logic
├── llm/        # Model Router (Groq/Gemini/Self-Hosted)
├── services/   # Lightning Vector Service 
└── workflow/   # Workflow Engine
```

## ❓ FAQ & Clarifications

### Why is there no local database?
The system is designed to use a managed/external **SQL Database** (MySQL/PostgreSQL) via the `DATABASE_URL` environment variable. This ensures data persistence and security are handled by a dedicated database provider.


