
# OpenClaw Architecture

## System Overview
The Gateway is the control plane.

## Components
### Gateway
Responsible for routing, sessions, execution.

### Channels
User-facing integrations.

### Agents
Reasoning layer.

### Tools
Execution layer.

### Providers
Model backends.

### Nodes
Distributed capabilities.

## Request Flow
User -> Channel -> Gateway -> Agent -> Tool/Provider -> Response

## Failure Domains
- Gateway
- Provider
- Channel
- Node
