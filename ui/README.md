# UI Component

Modern React-based web interface for digital forensic investigations.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Installation](#installation)
- [Features](#features)
- [Components](#components)
- [Development](#development)
- [Deployment](#deployment)

---

## Overview

The UI provides a complete investigation workflow:

**Core Features:**
- Investigation dashboard for case management
- Natural language chat interface with intelligent routing
- Evidence timeline builder with advanced filtering
- Event browser with JSONB field queries
- Investigation playbook manager
- Real-time agent progress via WebSocket
- Report generation (PDF and Markdown)

**User Experience:**
- Persistent filter state across tabs
- One-click query replication from chat to manual queries
- Expandable tool execution cards with copy-to-clipboard
- Dark mode support
- Responsive design for various screen sizes

### Technology Stack

- React 18.2 with TypeScript for type safety
- Vite for fast development and builds
- TailwindCSS 3.4 for styling
- React Router 6 for navigation
- Axios for API communication
- React Markdown for formatted responses

---

## Architecture

```
ui/
├── src/
│   ├── main.tsx                 # Application entry point
│   ├── App.tsx                  # Root component with routing
│   │
│   ├── pages/                   # Top-level pages
│   │   ├── Dashboard.tsx        # Investigation list
│   │   ├── Login.tsx            # Authentication
│   │   └── Settings.tsx         # User settings
│   │
│   ├── routes/                  # Route components
│   │   ├── Investigations.tsx   # Investigation CRUD
│   │   └── InvestigationDetail.tsx  # Single investigation view
│   │
│   ├── components/              # Reusable components
│   │   ├── Header.tsx           # Top navigation bar
│   │   ├── Sidebar.tsx          # Left sidebar
│   │   ├── EventsViewer.tsx     # Events table
│   │   ├── TimelineViewer.tsx   # Evidence timeline viewer
│   │   ├── FileDropzone.tsx     # Artifact upload
│   │   ├── ThemeToggle.tsx      # Dark/light mode
│   │   └── ApiDebugger.tsx      # API testing tool
│   │
│   ├── components/chat/         # Chat-specific components
│   │   ├── SimplifiedChatBox.tsx  # Main chat container
│   │   ├── ChatInput.tsx        # Message input with effort selector
│   │   ├── MessageRenderer.tsx  # Message type router
│   │   ├── UserMessageCard.tsx  # User message display
│   │   ├── AgentMessageCard.tsx # Agent message with tool executions
│   │   ├── ToolExecutionCard.tsx  # Tool execution display (expandable)
│   │   ├── SummaryCard.tsx      # Investigation summary
│   │   ├── ErrorCard.tsx        # Error message display
│   │   ├── LoadingState.tsx     # Loading indicators
│   │   ├── EmptyState.tsx       # Empty chat state
│   │   ├── UploadModal.tsx      # Artifact upload modal
│   │   ├── MutationConfirmation.tsx  # Mutation confirmation
│   │   └── ClarificationModal.tsx    # Clarification prompts
│   │

│   │
│   ├── contexts/                # React contexts
│   │   └── AuthContext.tsx      # Authentication state
│   │
│   ├── index.css                # Global styles (Tailwind)
│   └── vite-env.d.ts            # TypeScript declarations
│
├── public/                      # Static assets
├── index.html                   # HTML entry point
├── package.json                 # Node dependencies
├── tsconfig.json                # TypeScript config
├── vite.config.ts               # Vite config
├── tailwind.config.js           # Tailwind config
├── postcss.config.js            # PostCSS config
├── Dockerfile                   # Production container
└── README.md                    # This file
```

---

## Installation

### Docker (Recommended)

The UI runs as an nginx container serving static files:

```bash
# Build and start UI
docker compose up -d ui

# View UI logs
docker compose logs -f ui

# Rebuild after changes
docker compose build ui
docker compose up -d ui
```

### Manual Installation

For development:

```bash
cd ui

# Install Node.js 18+ (if not installed)
node --version  # Should be 18.0.0 or higher

# Install dependencies
npm install

# Start development server
npm run dev

# Access at http://localhost:5173
```

---

## Features

### 1. Investigation Dashboard

**Location**: `/` (root)

**Features**:
- View all investigations
- Create investigation
- Delete investigation
- Search/filter investigations
- View investigation metadata (created date, owner)

**First-time Login Behavior**:
- If no LLM configuration exists, users are automatically redirected to Settings
- A welcome banner explains the need to configure an LLM provider
- Once configured, users can access the dashboard and create investigations

**Screenshot Flow**:
```
Dashboard → Click "Create Investigation"
  → Enter title: "Ransomware Investigation - March 2024"
  → Click "Create"
  → Redirects to investigation detail page
```

### 2. Chat Interface

**Location**: `/investigations/{id}` (Chat tab)

**Features**:
- Ask natural language questions
- **Mode selector** - Choose routing mode (Auto/Agent/Timeline/Augmented Chat)
- **Effort selector** - Choose investigation depth (Quick/Standard/Thorough)
- **Routing feedback badges** - Visual indicators showing:
  - Which handler processed your query (Agent/RAG/Timeline/General Chat)
  - Selected playbook for agent investigations (e.g., "Lateral Movement Detection")
  - Handler-specific statistics (sources retrieved, entries affected, effort level, etc.)
  - Color-coded badges with icons for quick identification
- Real-time agent reasoning streaming (see agent's thought process)
- **Expandable tool execution cards** - Click to view arguments and results
- **RAG results display** - Query expansion and source retrieval shown as tool executions
- **Copy tool data to clipboard** - Copy arguments and results as JSON
- **Query replication buttons** - Replicate JSONB and event search queries to Events tab
- Markdown rendering with syntax highlighting
- Code block support
- Investigation statistics (events analyzed, timeline entries, turns, sources retrieved)
- Conversation history with message threading
- Stop agent execution at any time
- Continue incomplete investigations
- Delete messages

**Tool Execution Cards**:
- Compact display with expandable details
- Status indicators (executing, completed, failed)
- Turn counter (e.g., "1/10")
- Result summaries
- **"Query" button** - Appears on JSONB and event search tools
- Copy buttons for arguments and results
- Timeline registration indicators

**Query Replication**:
When the agent executes a query tool, you can replicate it in the Events tab:
- Click the tool execution to expand it
- Click the "Query" button
- Events tab opens with filters pre-populated
- Events tab badge flashes to indicate update
- Supports: `query_jsonb_field`, `query_jsonb_multiple`, `search_events_by_type`, `search_events_by_timerange`, `search_events_by_content`

**Example Interaction**:
```
User: "Find failed logon attempts"
  → API queues agent job
  → WebSocket streams agent reasoning:
    - Agent: "I'll count failed logons, find patterns, and register significant events"
    - Tool: "Counting evtx_security_4625 events..."
    - Result: "Found 42 events"
    - Agent: "Found 42 failed logon events. Now analyzing patterns..."
    - Tool: "Analyzing TargetUserName patterns..."
    - Result: "Top value: admin (18 occurrences)"
    - Agent: "User 'admin' was targeted 18 times from IP 10.50.30.15. Registering to timeline..."
    - Tool: "Adding to timeline: Failed logon: admin from 10.50.30.15"
    - Result: "Timeline entry created (entry 123)"
  → Agent completes with summary
  → Response displayed with markdown formatting and statistics
```

### 3. Evidence Timeline Viewer

**Location**: `/investigations/{id}` (Timeline tab)

**Features**:
- Chronological view of events, findings, and observations
- Filter by entry type (event, finding, observation, note)
- **Filter by event type** - Dropdown with all event types from timeline entries
- Filter by tags (suspicious, lateral_movement, persistence, etc.)
- **JSONB data field queries** - Query specific fields within timeline entry data
- Search by content (title, description, event data)
- Sort by timestamp (ascending/descending)
- View complete event data (auto-fetched from events table)
- Remove entries from timeline
- Add notes to timeline entries
- Pagination for large timelines
- **Persistent filters** - State preserved when switching tabs

**Entry Types**:
- **Event**: Forensic event from artifacts (login, process execution, file creation)
- **Finding**: High-level investigative conclusion
- **Observation**: Notable pattern or anomaly
- **Note**: User annotation or context

**Event Data Display**:
- Event ID and timestamp
- Event type (evtx_security_4624, mft_entry, etc.)
- Complete payload (all forensic fields)
- Source artifact
- Tags for categorization

**Advanced Query Builder**:
- Entry type filter (event, finding, observation, note)
- Event type filter with autocomplete dropdown
- Data field JSONB queries with field suggestions
- Date range filters
- Clear all filters button

### 4. Events Viewer

**Location**: `/investigations/{id}` (Events tab)

**Features**:
- Paginated event table (50 events per page)
- **Filter by event type** - Dropdown with all event types and counts
- **JSONB field queries** - Query specific fields within event payloads
- **Multiple JSONB filters** - Compound queries with breadcrumb display
- Filter by time range (start/end date)
- Search payload content (full-text search)
- Sort by timestamp (ascending/descending)
- View full event details (expandable JSON)
- **Add events to timeline** - One-click timeline entry creation
- **Copy JSON to clipboard** - Copy event payloads
- **Persistent filters** - State preserved when switching tabs

**Advanced Query Builder**:
- Event type filter with autocomplete dropdown
- JSONB field path with field suggestions (context-aware)
- Operator selection (=, !=, >, <, LIKE, ILIKE, CONTAINS, etc.)
- Value input with examples
- Multiple filters with breadcrumb display
- Date range filters
- Clear all filters button

**Dynamic Field Suggestions**:
- Field suggestions update based on selected event type
- Shows only relevant fields for the filtered event type
- Autocomplete dropdown with keyboard navigation
- "Show all fields" button to browse available fields

**Columns**:
- Timestamp
- Event Type (badge)
- Artifact ID
- Payload (truncated, expandable)
- Event ID
- Actions (expand, add to timeline)

### 5. Artifact Upload

**Location**: `/investigations/{id}` (Upload button)

**Features**:
- Drag-and-drop file upload
- Multi-file upload
- Progress indicators
- Automatic parsing job creation
- Supported formats: `.evtx`, `.pf`, `.lnk`, `$MFT`, registry hives

### 6. Playbook Manager

**Location**: `/playbooks`

**Features**:
- View all playbooks (base + custom)
- Search playbooks by name or description
- **Base Playbooks** (20 built-in, immutable):
  - View playbook content with syntax highlighting
  - Clone to create editable copies
  - Always enabled for all investigations
- **Custom Playbooks** (user-created, mutable):
  - Create playbooks from scratch
  - Edit existing playbooks (name, description, content)
  - Delete playbooks
  - Enable/disable globally
  - Clone from other custom playbooks
- **Markdown Editor**:
  - Rich text editing with validation
  - Syntax highlighting for code blocks
  - Real-time preview
- **Per-Investigation Control** (API ready):
  - Enable/disable specific playbooks per investigation
  - Persistent settings across sessions

**Playbook Structure**:
```yaml
name: lateral_movement
description: Investigation strategies for detecting lateral movement
playbook: |
  ## LATERAL MOVEMENT INVESTIGATION PLAYBOOK
  
  ### Key Indicators to Investigate:
  1. Network Logons (Event ID 4624 Type 10)
  2. Explicit Credential Usage (Event ID 4648)
  ...
```

**Example Workflow**:
```
1. Browse base playbooks → Find "Lateral Movement"
2. Click "Clone" → Creates "lateral_movement_copy"
3. Click "Edit" → Customize for your environment
4. Save → Available for all investigations
5. (Optional) Enable/disable per investigation via API
```

### 7. Settings Panel

**Location**: `/settings`

**Features**:
- LLM provider configuration
- API endpoint settings
- Model selection
- Temperature control
- Max context length
- API key management (encrypted)
- Active config selection

**First-time Setup**:
- Users without an LLM configuration are automatically redirected here after login
- A welcome banner provides guidance on configuring the LLM provider
- Configuration is required before the system can process natural language queries

---

## Components

#### RoutingBadge.tsx

Routing feedback component:
- Displays handler type with color-coded badge and icon
- Shows handler-specific statistics
- Displays playbook information for agent investigations
- Responsive design with proper dark mode support

```tsx
<RoutingBadge
  handlerType="agent"
  handlerDisplayName="AI Agent Investigation"
  playbookName="lateral_movement"
  playbookDisplayName="Lateral Movement Detection"
  stats={{
    effort_level: "medium",
    max_turns: 10
  }}
/>
```

**Color Scheme**:
- Agent: Purple (`bg-purple-100 dark:bg-purple-900/30`)
- RAG: Blue (`bg-blue-100 dark:bg-blue-900/30`)
- Timeline: Green (`bg-green-100 dark:bg-green-900/30`)
- General Chat: Gray (`bg-gray-100 dark:bg-gray-900/30`)

### Core Components

#### Header.tsx

Top navigation bar with:
- Application logo
- Investigation title
- User menu (logout)
- Theme toggle

```tsx
<Header
  investigationTitle="Ransomware Investigation"
  userName="admin"
  onLogout={() => navigate('/login')}
/>
```

#### Sidebar.tsx

Left sidebar navigation:
- Dashboard link
- Settings link
- Documentation link
- Audit log link

```tsx
<Sidebar currentPath="/investigations" />
```

### Chat Components

#### SimplifiedChatBox.tsx

Main chat container with:
- Message history
- Input field
- WebSocket connection
- Auto-scroll to bottom
- Loading states
- Effort level selector (Quick, Standard, Thorough)
- Query replication callback

```tsx
<SimplifiedChatBox
  investigationId={investigationId}
  onGraphUpdated={() => refreshTimeline()}
  onReplicateQuery={(params) => handleQuery(params)}
/>
```

#### MessageRenderer.tsx

Message type router:
- Routes messages to appropriate card components based on `message_type`
- User messages → `UserMessageCard`
- Agent messages → `AgentMessageCard`
- Tool executions → `ToolExecutionCard`
- Summaries → `SummaryCard`
- Errors → `ErrorCard`

```tsx
<MessageRenderer
  message={message}
  isStreaming={isStreaming}
  onDelete={deleteMessage}
  onEdit={editMessage}
  onContinue={continueInvestigation}
  onReplicateQuery={replicateQuery}
/>
```

#### AgentMessageCard.tsx

Agent message display:
- **Routing badge** - Shows handler type, playbook name, and statistics
- Chronological event stream (thinking + tool executions)
- Markdown rendering with syntax highlighting
- Tool execution cards (expandable)
- Investigation statistics (small counters)
- Continuation UI for incomplete investigations
- Copy message button
- Delete message button

**Routing Badge Display**:
- **Agent Handler**: Purple badge with CPU chip icon
  - Shows playbook name (e.g., "Lateral Movement Detection")
  - Displays effort level and max turns (e.g., "medium effort • 6 turns max")
- **RAG Handler**: Blue badge with sparkles icon
  - Shows sources retrieved and expansion terms (e.g., "50 sources • 7 terms")
- **Timeline Handler**: Green badge with clock icon
  - Shows operation type and entries affected (e.g., "query • 5 entries")
- **General Chat Handler**: Gray badge with chat icon
  - Shows query type (e.g., "metadata")

```tsx
<AgentMessageCard
  message={message}
  isStreaming={false}
  onDelete={(id) => deleteMessage(id)}
  onContinue={(jobId, effort) => continueJob(jobId, effort)}
  onReplicateQuery={(params) => replicateToEvents(params)}
/>
```

#### ToolExecutionCard.tsx

Tool execution display:
- Compact header with tool name and status
- Expandable arguments and results
- **Copy buttons** for arguments and results (JSON)
- **"Query" button** for JSONB and event search tools
- Timeline registration indicators
- Turn counter
- Result summaries

```tsx
<ToolExecutionCard
  toolExecution={tool}
  onReplicateQuery={(params) => replicateQuery(params)}
/>
```

### Events & Timeline Components

#### EventsViewer.tsx

Event browsing and filtering:
- Two-column layout (events list + query builder)
- Paginated event list
- Event type filter with autocomplete
- JSONB field queries with breadcrumbs
- Date range filters
- Full-text search
- Expandable event details
- Add to timeline button
- **Dynamic field suggestions** - Updates based on event type filter
- **Persistent state** - Filters preserved when switching tabs

```tsx
<EventsViewer
  investigationId={investigationId}
  replicatedQuery={queryParams}
  onQueryApplied={() => clearQuery()}
/>
```

#### TimelineViewer.tsx

Timeline browsing and filtering:
- Entry type filter (event, finding, observation, note)
- Event type filter with autocomplete
- JSONB data field queries
- Date range filters
- Search by title/description
- Expandable entry details
- Remove from timeline button
- Notes display
- **Persistent state** - Filters preserved when switching tabs

```tsx
<TimelineViewer
  investigationId={investigationId}
/>
```

### Utility Components

#### FileDropzone.tsx

Drag-and-drop file upload:
- Multiple file support
- File type validation
- Size limit enforcement
- Progress tracking
- Error handling

```tsx
<FileDropzone
  investigationId={investigationId}
  onUploadComplete={(files) => console.log(files)}
  maxSizeMB={500}
  acceptedTypes={['.evtx', '.pf', '.lnk']}
/>
```

#### ThemeToggle.tsx

Dark/light mode toggle:
- Persists to localStorage
- Smooth transitions
- System preference detection

```tsx
<ThemeToggle />
```

---

## Development

### Running Dev Server

```bash
# Start dev server (hot reload enabled)
npm run dev

# Access at http://localhost:5173
# API proxy configured in vite.config.ts
```

### Building for Production

```bash
# Build static files
npm run build

# Output to dist/
# Preview production build
npm run preview
```

### Code Style

```bash
# Format code (Prettier)
npm run format

# Lint code (ESLint)
npm run lint

# Type check
npm run type-check
```

### Environment Variables

Create `.env.local` for local development:

```bash
# Development mode (direct API access)
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000

# Docker Compose mode (via nginx proxy)
VITE_API_URL=https://localhost
VITE_WS_URL=wss://localhost
```

### Adding Pages

1. Create page component in `src/pages/`:
   ```tsx
   // src/pages/MyPage.tsx
   export default function MyPage() {
     return (
       <div className="p-6">
         <h1 className="text-2xl font-bold">My Page</h1>
       </div>
     );
   }
   ```

2. Add route in `src/App.tsx`:
   ```tsx
   import MyPage from './pages/MyPage';
   
   <Route path="/my-page" element={<MyPage />} />
   ```

3. Add navigation link in `src/components/Sidebar.tsx`:
   ```tsx
   <Link to="/my-page">My Page</Link>
   ```

### Adding Components

1. Create component file:
   ```tsx
   // src/components/MyComponent.tsx
   interface MyComponentProps {
     title: string;
     onAction: () => void;
   }
   
   export default function MyComponent({ title, onAction }: MyComponentProps) {
     return (
       <div className="bg-white rounded shadow p-4">
         <h2>{title}</h2>
         <button onClick={onAction}>Action</button>
       </div>
     );
   }
   ```

2. Import and use:
   ```tsx
   import MyComponent from './components/MyComponent';
   
   <MyComponent
     title="Hello"
     onAction={() => console.log('clicked')}
   />
   ```

---

## Deployment

### Docker Production Build

The `Dockerfile` creates a multi-stage build:

```dockerfile
# Stage 1: Build
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 443
CMD ["nginx", "-g", "daemon off;"]
```

### Nginx Configuration

Create `nginx.conf` for production:

```nginx
server {
    listen 443 ssl;
    server_name localhost;
    
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    root /usr/share/nginx/html;
    index index.html;
    
    # SPA routing
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # API proxy
    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # WebSocket proxy
    location /api/v1/chat/ws {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Environment-Specific Builds

Use build-time environment variables:

```bash
# Development (direct API access)
VITE_API_URL=http://localhost:8000 npm run build

# Docker Compose (via nginx proxy)
VITE_API_URL=https://localhost npm run build

# Staging
VITE_API_URL=https://staging-api.example.com npm run build

# Production
VITE_API_URL=https://api.example.com npm run build
```

---

## Styling

### TailwindCSS

The UI uses Tailwind for styling:

```tsx
// Utility classes
<div className="bg-blue-500 text-white p-4 rounded-lg shadow-md">
  Hello World
</div>

// Responsive design
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
  {items.map(item => <Card key={item.id} {...item} />)}
</div>

// Dark mode support
<div className="bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100">
  Content
</div>
```

### Custom CSS

Global styles in `src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer components {
  .btn-primary {
    @apply bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded;
  }
}
```

---

## WebSocket Integration

### Connection Management

```tsx
// src/components/chat/ChatBox.tsx
const [ws, setWs] = useState<WebSocket | null>(null);

useEffect(() => {
  const token = localStorage.getItem('token');
  // Use environment variable for WebSocket URL
  const wsBaseUrl = import.meta.env.VITE_WS_URL || 'wss://localhost';  // Default to nginx proxy
  const wsUrl = `${wsBaseUrl}/api/v1/chat/ws/${investigationId}?token=${token}`;
  
  const websocket = new WebSocket(wsUrl);
  
  websocket.onopen = () => {
    console.log('WebSocket connected');
  };
  
  websocket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleWebSocketMessage(data);
  };
  
  websocket.onerror = (error) => {
    console.error('WebSocket error:', error);
  };
  
  websocket.onclose = () => {
    console.log('WebSocket closed');
    // Attempt reconnect after 5 seconds
    setTimeout(() => connectWebSocket(), 5000);
  };
  
  setWs(websocket);
  
  return () => {
    websocket.close();
  };
}, [investigationId]);
```

### Message Handling

```tsx
function handleWebSocketMessage(data: any) {
  switch (data.type) {
    case 'agent_thinking':
      setStreamingContent(prev => prev + data.thought);
      break;
    case 'agent_tool_call':
      addMessage({
        role: 'system',
        content: `Calling tool: ${data.tool_name}`
      });
      break;
    case 'agent_completed':
      setStreamingContent('');
      addMessage({
        role: 'assistant',
        content: data.summary
      });
      break;
    case 'job_failed':
      showError(data.error);
      break;
  }
}
```

---

## API Integration

### Axios Configuration

```tsx
// src/lib/api.ts
import axios from 'axios';

  const api = axios.create({
    baseURL: import.meta.env.VITE_API_URL || 'https://localhost',  // Default to nginx proxy
    headers: {
      'Content-Type': 'application/json'
  }
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
```

### API Calls

```tsx
// Fetch investigations
const fetchInvestigations = async () => {
  const response = await api.get('/api/v1/investigations');
  return response.data;
};

// Create investigation
const createInvestigation = async (title: string) => {
  const response = await api.post('/api/v1/investigations', { title });
  return response.data;
};

// Upload artifact
const uploadArtifact = async (file: File, investigationId: string) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('investigation_id', investigationId);
  
  const response = await api.post('/api/v1/artifacts/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return response.data;
};
```

---

## Key Features

### Query Replication

Replicate agent queries to the Events tab for manual exploration:

1. **Agent executes a query tool** (JSONB, event search, time range, etc.)
2. **Expand the tool execution card** in chat
3. **Click "Query" button** (appears on query tools only)
4. **Events tab opens** with filters pre-populated
5. **Events tab badge flashes** to indicate update
6. **Explore results** with full query builder capabilities

**Supported Tools**:
- `query_jsonb_field` - Replicates JSONB path, operator, value, and event_type
- `query_jsonb_multiple` - Replicates multiple JSONB conditions
- `search_events_by_type` - Replicates event_type filter
- `search_events_by_timerange` - Replicates start/end dates and event_type
- `search_events_by_content` - Replicates search text and event_type

**RAG Tool Executions** (Augmented Chat mode):
- `expand_query` - Shows LLM-generated search terms with full expansion details
- `retrieve_sources` - Shows all retrieved sources with scores, owner types, and full text (expandable)

### Dynamic Field Suggestions

Field suggestions automatically update based on context:

**Events Tab**:
- Select an event type filter → Field suggestions update to show only fields from that event type
- Clear event type filter → Field suggestions show all fields from all event types
- Autocomplete dropdown with keyboard navigation (arrow keys, enter, escape)

**Timeline Tab**:
- Select an event type filter → Field suggestions update based on timeline entries with that event type
- Shows fields from both timeline entry `data` and linked event payloads

### Persistent Filter State

Filters are preserved when switching between tabs:
- Apply filters in Events tab → Switch to Timeline → Switch back → Filters still active
- Components remain mounted but hidden (CSS `display: none`)
- No re-fetching or state loss
- Better performance and user experience

---

## Troubleshooting

### CORS Errors

**Symptoms**: `Access-Control-Allow-Origin` errors in browser console

**Solution**: Verify API CORS configuration allows UI origin:
```python
# api/app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Add UI URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### WebSocket Connection Failed

**Symptoms**: WebSocket shows "disconnected" in console

  **Solutions**:
  - Verify nginx is running: `docker compose ps ui`
  - Verify API is accessible: `curl -k https://localhost/api/health` (Docker) or `curl http://localhost:8000/health` (dev)
  - Check JWT token is valid: `localStorage.getItem('token')`
  - Verify WebSocket URL:
    - Docker: `wss://localhost/api/v1/chat/ws/{id}`
    - Development: `ws://localhost:8000/api/v1/chat/ws/{id}`

### Events API 500 Error with Date Filters

**Symptoms**: "Error loading events" when using date filters

**Cause**: Date strings not being parsed to datetime objects

**Solution**: Ensure `dateutil` is installed in API:
```bash
pip install python-dateutil
```

The API automatically parses ISO date strings to datetime objects.

### Build Errors

**Symptoms**: `npm run build` fails

**Solutions**:
```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install

# Clear Vite cache
rm -rf .vite

# Update dependencies
npm update
```

---

## RAG Feature

### Configuration

To enable Augmented Chat mode, configure embedding provider in Settings:

1. **Navigate to Settings** → LLM Configuration
2. **Scroll to Embedding Configuration section**
3. **Select embedding provider**:
   - OpenAI: `text-embedding-ada-002` (1536 dimensions)
   - Cohere: `embed-english-v3.0` (1024 dimensions)
   - Ollama: Local embedding models (e.g., `nomic-embed-text`)
4. **Enter embedding API URL**:
   - OpenAI: `https://api.openai.com/v1/embeddings`
   - Ollama: `http://host.docker.internal:11434/v1/embeddings`
   - LM Studio: `http://host.docker.internal:1234/v1/embeddings`
5. **Enter API key** (if required)
6. **Enter model name**
7. **Save configuration**

### Usage

1. **Upload and parse artifacts** - Embeddings are automatically generated
2. **Select "Augmented Chat" mode** in chat input
3. **Ask semantic questions**:
   - "Is there evidence of credential access?"
   - "Find lateral movement indicators"
   - "Search for privilege escalation"
4. **View results**:
   - Query Expansion tool shows generated search terms (expandable)
   - Retrieved Sources tool shows all matched events (expandable with full text)
   - LLM answer cites sources by number
5. **Review later** - Tool executions persist to database and reload on page refresh

### How It Works

1. **Automatic Embedding** - During artifact parsing:
   - Interesting events are filtered (Sysmon process creation, security events, etc.)
   - Events are batched (50 per API call)
   - Embeddings are generated and stored in PGVector
   - Embeddings linked to events via `owner_type='tool'`, `owner_id=event_id`

2. **Query Expansion** - When user asks a question:
   - LLM generates 5-7 contextual search terms
   - Example: "credential access" → "lsass.exe", "mimikatz", "SAM database"
   - Saved as tool execution with expanded terms in result

3. **Multi-Query Retrieval** - Search with multiple queries:
   - Generate embeddings for original + expanded queries
   - Search PGVector with each embedding (10 results per query)
   - Merge all results (up to 80 candidates)

4. **Deduplication & Re-ranking**:
   - Remove duplicates by event ID
   - Sort by similarity score
   - Take top 50 sources
   - Saved as single tool execution with all sources

5. **LLM Synthesis**:
   - Build context from top 50 sources
   - LLM generates answer citing sources
   - Tool executions saved for later review

### Tool Execution Display

RAG results are displayed as expandable tool execution cards:

**Query Expansion**:
- Collapsed: "Query Expansion - Complete"
- Expanded: Shows all generated search terms in JSON format

**Retrieved Sources (X results)**:
- Collapsed: "Retrieved Sources (50 results) - Complete"
- Expanded: Shows all sources with:
  - Index number
  - Owner type (tool, timeline, chat, note)
  - Owner ID (event_id, entry_id, etc.)
  - Similarity score
  - Text preview (200 chars)
  - Full text (complete event data)

## Routing System Extensibility

### Adding Handlers

The routing system is designed to be extensible. To add a handler:

**Backend** (`api/app/services/handlers/`):

1. **Create handler module**:
   ```python
   # api/app/services/handlers/my_handler.py
   async def handle_my_operation(
       db: AsyncSession,
       investigation_id: UUID,
       user_query: str,
       user_id: int,
   ) -> Dict[str, Any]:
       # Process query
       result = await process_query(...)
       
       return {
           "type": "my_handler_answer",
           "success": True,
           "message": result,
           "routing_metadata": {
               "handler_type": "my_handler",
               "handler_display_name": "My Custom Handler",
               "custom_stat_1": 42,
               "custom_stat_2": "value",
           },
       }
   ```

2. **Add routing metadata schema** (`api/app/schemas/routing_metadata.py`):
   ```python
   class MyHandlerMetadata(HandlerMetadata):
       handler_type: str = "my_handler"
       handler_display_name: str = "My Custom Handler"
       processing_time_ms: Optional[int] = None
       
       custom_stat_1: int = Field(0, description="Description")
       custom_stat_2: str = Field("", description="Description")
   ```

3. **Add intent type** (`api/app/schemas/chat_message.py`):
   ```python
   class IntentType(str, Enum):
       MY_OPERATION = "my_operation"
   ```

4. **Update classification prompt** (`api/app/services/chat_router.py`):
   - Add intent category to `CLASSIFICATION_PROMPT_SYSTEM`
   - Add routing case in `route_chat_message()`

**Frontend** (`ui/src/components/chat/`):

1. **Update RoutingBadge component**:
   ```tsx
   // Add icon mapping
   case 'my_handler':
     return <MyIcon className="w-4 h-4" />;
   
   // Add color mapping
   case 'my_handler':
     return 'bg-orange-100 text-orange-800 ...';
   
   // Add stats formatting
   if (handlerType === 'my_handler') {
     parts.push(`${stats.custom_stat_1} items`);
   }
   ```

2. **Handler automatically displays** - No changes needed to `AgentMessageCard`

### Handler Plugin Pattern

All handlers follow a consistent interface:

```python
async def handle_X(
    db: AsyncSession,
    investigation_id: UUID,
    user_query: str,
    user_id: int,
) -> Dict[str, Any]:
    """Process query and return result with routing metadata."""
    return {
        "success": bool,
        "message": str,
        "routing_metadata": {
            "handler_type": str,
            "handler_display_name": str,
            # ... handler-specific stats
        },
    }
```

This makes the system **fully extensible** - add handlers without modifying core routing logic.

## Further Reading

- [API Documentation](../api/README.md) - Backend API reference
- [Worker Documentation](../api/worker/README.md) - Agent execution
- [React Documentation](https://react.dev/) - React framework
- [Vite Documentation](https://vitejs.dev/) - Build tool
- [TailwindCSS Documentation](https://tailwindcss.com/) - CSS framework

---

**Questions or issues?** Open an issue on GitHub or check the main [README](../README.md).
