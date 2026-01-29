# Open Agent Investigation Documentation

A micro-forensics workbench for analyzing artifacts.

## Documentation Structure

### Getting Started

- [Installation](getting-started.md) - System requirements, installation methods, and initial configuration
- [Quickstart](quickstart.md) - Minimal working example to get started in 5 minutes

### Core Concepts

- [Architecture](architecture.md) - System design, components, and data flow
- [Query Routing](architecture.md#query-routing) - Intelligent handler selection and execution modes
- [Evidence Timeline](architecture.md#evidence-timeline) - Event-first timeline design

### User Guide

- [User Guide](user-guide.md) - Common workflows and usage patterns
- [Uploading Artifacts](user-guide.md#uploading-artifacts) - Supported file types and parsing
- [Asking Questions](user-guide.md#asking-questions) - Query modes and effort levels
- [Timeline Management](user-guide.md#timeline-management) - Building and filtering evidence timelines
- [Report Generation](user-guide.md#report-generation) - Creating investigation reports
- [Investigation Playbooks](playbooks.md) - Built-in attack scenario guidance (21 playbooks)


### Technical Reference

- [Investigation Playbooks](playbooks.md) - Attack scenario playbooks and customization
- [API Documentation](../api/README.md) - REST API endpoints and WebSocket support
- [Worker Architecture](../api/worker/README.md) - Artifact parsing and agent execution

### Additional Resources

- [License](../LICENSE) - GNU General Public License v3.0


## Getting Help

- **GitHub Issues**: Report bugs or request features at https://github.com/eheuser/open-agent-investigation/issues
- **Discussions**: Ask questions at https://github.com/eheuser/open-agent-investigation/discussions
- **Documentation**: Browse this documentation for detailed information

## License

Open Agent Investigation is licensed under the GNU General Public License v3.0. See [LICENSE](../LICENSE) for the full license text.
