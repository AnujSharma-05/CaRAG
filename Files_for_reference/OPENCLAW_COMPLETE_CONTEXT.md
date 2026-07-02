
# OpenClaw Complete Context

## Executive Summary
OpenClaw is a gateway-centric AI agent orchestration platform.

## Core Concepts
- Gateway
- Agents
- Nodes
- Channels
- Tools
- Skills
- Plugins
- Providers
- Sessions
- Context

## Architecture
Gateway
├── Channels
├── Sessions
├── Agents
├── Tools
├── Skills
├── Plugins
├── Providers
└── Nodes

## Context Pipeline
Incoming Message -> Session -> Memory -> Skills -> Tools -> Agent -> Provider -> Model

## Tools vs Skills vs Plugins
### Tools
Executable capabilities.

### Skills
Instruction and workflow packages.

### Plugins
Runtime extensions.

## CLI Reference
- openclaw configure
- openclaw gateway
- openclaw models
- openclaw memory
- openclaw logs
- openclaw nodes

## Deployment
- Local
- Docker
- Production

## Troubleshooting
- Gateway health
- Provider connectivity
- Channel auth
- Session routing

## AI Operating Knowledge
Agents reason.
Tools act.
Skills instruct.
Plugins extend.
