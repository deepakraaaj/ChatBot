# LightningBot - System Architecture Diagram

## Complete System Architecture

```mermaid
graph TB
    subgraph "Client Layer"
        User([Users/Applications])
    end
    
    subgraph "API Gateway Layer"
        User -->|HTTPS| ReverseProxy[Reverse Proxy / Load Balancer]
        ReverseProxy -->|Route| FastAPI[FastAPI Backend<br/>Port 8000]
    end
    
    subgraph "Authentication & Security"
        FastAPI -->|Validate| Auth[JWT Authentication]
        Auth -->|Check| Guardrails[Security Guardrails]
    end
    
    subgraph "Core Processing Engine"
        Guardrails -->|Process| StreamManager[Stream Manager]
        StreamManager -->|Initialize| GraphEngine[LangGraph State Machine]
        
        subgraph "Graph Nodes"
            GraphEngine -->|Entry| N1[Understanding Node]
            N1 -->|SQL Intent| N2[SQL Planning Node]
            N1 -->|Workflow Intent| N3[Workflow Engine Node]
            N1 -->|Chat Intent| N4[Reply Node]
            N2 -->|Execute| N5[SQL Execution Node]
            N5 --> N4
            N3 --> N4
        end
    end
    
    subgraph "Service Layer"
        N1 & N2 & N3 & N4 -.->|Use| VectorSvc[Vector Service]
        N1 & N4 -.->|Use| HistorySvc[History Service]
        N1 -.->|Use| UserCtxSvc[User Context Service]
        N3 -.->|Use| WorkflowSvc[Workflow State Service]
        N2 -.->|Use| SchemaSvc[Schema Service]
        StreamManager -.->|Use| MetricsSvc[Metrics Service]
    end
    
    subgraph "LLM Provider Layer"
        N1 & N2 & N4 -->|Route| LLMRouter[LLM Router]
        LLMRouter -->|Primary| SelfHosted[Self-Hosted LLM<br/>FastQwenRunner]
        LLMRouter -->|Fallback| Groq[Groq API]
        LLMRouter -->|Alternative| Bedrock[AWS Bedrock]
    end
    
    subgraph "Data Infrastructure"
        direction TB
        
        subgraph "Vector Search"
            VectorSvc -->|Search| ES[(Elasticsearch<br/>Port 9201)]
            VectorSvc -->|Cache| Redis1[Redis Cache Layer]
        end
        
        subgraph "Caching Layer"
            Redis1[(Redis<br/>Port 6380)]
            VectorSvc & N2 -.->|Cache| Redis1
        end
        
        subgraph "Persistent Storage"
            HistorySvc -->|Save/Load| MySQL[(MySQL Database)]
            UserCtxSvc -->|Load| MySQL
            WorkflowSvc -->|Save/Load| MySQL
            SchemaSvc -->|Fetch| MySQL
            MetricsSvc -->|Record| MySQL
            N5 -->|Execute| MySQL
        end
    end
    
    subgraph "Monitoring & Analytics"
        MetricsSvc -->|Expose| Dashboard[Streamlit Dashboard<br/>Port 8501]
        Dashboard -->|Query| FastAPI
    end
    
    subgraph "External Services"
        N5 -.->|Query| ExternalDB[(External Databases)]
        FastAPI -.->|Notify| Mailer[Email Service]
    end
    
    GraphEngine -.->|Final State| StreamManager
    StreamManager -->|Stream| User
    
    classDef gateway fill:#ffcccc,stroke:#cc0000,stroke-width:2px,color:#000;
    classDef processing fill:#ccffcc,stroke:#00cc00,stroke-width:2px,color:#000;
    classDef service fill:#ccccff,stroke:#0000cc,stroke-width:2px,color:#000;
    classDef storage fill:#ffccff,stroke:#cc00cc,stroke-width:2px,color:#000;
    classDef llm fill:#ffffcc,stroke:#cccc00,stroke-width:2px,color:#000;
    classDef monitoring fill:#ffebcc,stroke:#ff8800,stroke-width:2px,color:#000;
    
    class ReverseProxy,FastAPI,Auth,Guardrails gateway;
    class StreamManager,GraphEngine,N1,N2,N3,N4,N5 processing;
    class VectorSvc,HistorySvc,UserCtxSvc,WorkflowSvc,SchemaSvc,MetricsSvc service;
    class ES,Redis1,MySQL,ExternalDB storage;
    class LLMRouter,SelfHosted,Groq,Bedrock llm;
    class Dashboard,Mailer monitoring;
```

## Container Deployment View

```mermaid
graph LR
    subgraph "Docker Compose Stack"
        subgraph "Backend Container"
            BE[lightning_backend<br/>FastAPI + LangGraph<br/>Port: 8000]
        end
        
        subgraph "Search Container"
            ESC[lightning_es<br/>Elasticsearch 8.17<br/>Port: 9201]
        end
        
        subgraph "Cache Container"
            RC[lightning_redis<br/>Redis 7.2<br/>Port: 6380]
        end
        
        subgraph "Dashboard Container"
            DC[lightning_dashboard<br/>Streamlit<br/>Port: 8501]
        end
        
        BE <-->|Vector Search| ESC
        BE <-->|Caching| RC
        DC -->|API Calls| BE
    end
    
    subgraph "External Dependencies"
        ExtDB[(External MySQL<br/>via DATABASE_URL)]
        ExtLLM[Self-Hosted LLM<br/>FastQwenRunner]
        CloudLLM[Cloud LLM Providers<br/>Groq / Bedrock]
    end
    
    BE <-->|SQL Queries| ExtDB
    BE -->|LLM Requests| ExtLLM
    BE -->|Fallback| CloudLLM
    
    Client([Client Applications]) -->|HTTPS| BE
    Client -->|View Metrics| DC
    
    classDef container fill:#e1f5ff,stroke:#01579b,stroke-width:3px;
    classDef external fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    
    class BE,ESC,RC,DC container;
    class ExtDB,ExtLLM,CloudLLM external;
```

## Request Processing Flow

```mermaid
graph TB
    Start([Client Request]) -->|POST /chat| API[FastAPI Endpoint]
    
    API --> Auth{JWT Valid?}
    Auth -->|No| Reject[401 Unauthorized]
    Auth -->|Yes| Guard{Safe Input?}
    
    Guard -->|No| Block[400 Bad Request]
    Guard -->|Yes| Load[Load Context]
    
    Load --> History[Chat History]
    Load --> UserCtx[User Context]
    Load --> WFState[Workflow State]
    
    History & UserCtx & WFState --> Init[Initialize Graph State]
    
    Init --> Understanding[Understanding Node]
    
    Understanding --> Classify{Intent?}
    
    Classify -->|SQL| SQLPlan[SQL Planning]
    Classify -->|Workflow| WFEngine[Workflow Engine]
    Classify -->|Chat| Reply[Reply Generation]
    
    SQLPlan --> Valid{Valid SQL?}
    Valid -->|Yes| SQLExec[SQL Execution]
    Valid -->|No| Reply
    
    SQLExec --> Format[Format Results]
    Format --> Reply
    
    WFEngine --> Step[Process Step]
    Step --> SaveWF[Save Workflow State]
    SaveWF --> Reply
    
    Reply --> Vector[Vector Context]
    Vector --> Generate[Generate Response]
    
    Generate --> Stream[Stream Tokens]
    Stream --> Save[Save History & Metrics]
    Save --> Response([Return to Client])
    
    classDef decision fill:#fff9c4,stroke:#f57f17,stroke-width:2px;
    classDef process fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px;
    classDef endpoint fill:#ffccbc,stroke:#d84315,stroke-width:2px;
    
    class Classify,Valid,Auth,Guard decision;
    class Understanding,SQLPlan,SQLExec,WFEngine,Reply,Generate process;
    class Start,Response,Reject,Block endpoint;
```

## Data Flow Architecture

```mermaid
graph LR
    subgraph "Input Layer"
        I1[User Message] --> I2[Security Check]
        I2 --> I3[Load History]
        I3 --> I4[Load Context]
    end
    
    subgraph "Processing Layer"
        I4 --> P1[Intent Classification]
        P1 --> P2{Route}
        
        P2 -->|SQL| S1[Schema Fetch]
        S1 --> S2[SQL Generation]
        S2 --> S3[SQL Execution]
        S3 --> S4[Result Format]
        
        P2 -->|Workflow| W1[Load State]
        W1 --> W2[Process Step]
        W2 --> W3[Save State]
        
        P2 -->|Chat| C1[Vector Search]
        C1 --> C2[Context Retrieval]
    end
    
    subgraph "Response Layer"
        S4 --> R1[Aggregate Context]
        W3 --> R1
        C2 --> R1
        
        R1 --> R2[Generate Response]
        R2 --> R3[Stream Output]
    end
    
    subgraph "Persistence Layer"
        R3 --> D1[Save History]
        R3 --> D2[Save Workflow]
        R3 --> D3[Save Metrics]
    end
    
    D1 & D2 & D3 --> Output[Client Response]
    
    classDef input fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef process fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px;
    classDef response fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef persist fill:#fff3e0,stroke:#ef6c00,stroke-width:2px;
    
    class I1,I2,I3,I4 input;
    class P1,P2,S1,S2,S3,S4,W1,W2,W3,C1,C2 process;
    class R1,R2,R3 response;
    class D1,D2,D3,Output persist;
```

## Component Interaction Matrix

| Component | Elasticsearch | Redis | MySQL | LLM Router | Vector Service | History Service |
|-----------|--------------|-------|-------|------------|----------------|-----------------|
| **Understanding Node** | ✓ (via Vector) | ✓ (cache) | ✓ (context) | ✓ | ✓ | ✓ |
| **SQL Planning Node** | - | ✓ (cache) | ✓ (schema) | ✓ | - | - |
| **SQL Execution Node** | - | - | ✓ (execute) | - | - | - |
| **Workflow Engine** | - | - | ✓ (state) | ✓ | - | - |
| **Reply Node** | ✓ (via Vector) | ✓ (cache) | - | ✓ | ✓ | - |
| **Stream Manager** | - | - | ✓ (save) | - | - | ✓ |

## Technology Stack

```mermaid
graph TB
    subgraph "Application Layer"
        A1[FastAPI 0.100+]
        A2[LangGraph]
        A3[LangChain Core]
        A4[Streamlit]
    end
    
    subgraph "AI/ML Layer"
        M1[Sentence Transformers]
        M2[Groq SDK]
        M3[Custom LLM Clients]
    end
    
    subgraph "Data Layer"
        D1[SQLAlchemy 2.0]
        D2[Elasticsearch Client]
        D3[Redis Client]
    end
    
    subgraph "Infrastructure"
        I1[Docker Compose]
        I2[Uvicorn ASGI]
        I3[Async IO]
    end
    
    A1 & A2 & A3 --> M1 & M2 & M3
    A1 & A2 --> D1 & D2 & D3
    A1 & A4 --> I1 & I2 & I3
```

## Key Features

### Performance Optimizations
- **Redis Caching**: Multi-level caching for embeddings, SQL queries, and LLM responses
- **Elasticsearch Bulk API**: High-throughput document indexing
- **Connection Pooling**: Optimized database and cache connections
- **Async Processing**: Non-blocking I/O for all external calls

### Reliability Features
- **LLM Fallback Chain**: Primary → Fallback → Production provider routing
- **Health Checks**: Provider availability monitoring
- **Error Handling**: Graceful degradation and error recovery
- **State Persistence**: Workflow state recovery across sessions

### Security Measures
- **JWT Authentication**: Token-based user authentication
- **Input Guardrails**: Malicious content detection and blocking
- **SQL Injection Prevention**: Parameterized queries and validation
- **CORS Configuration**: Controlled cross-origin access
