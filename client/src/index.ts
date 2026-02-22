/**
 * AgentLink TypeScript Client
 * 
 * TODO: Implement by Lilith
 * - AgentLinkClient class
 * - WebSocket connection
 * - State CRUD operations
 * - OpenClaw plugin interface
 */

export interface AgentLinkConfig {
  url: string;
  agentId: string;
  secret?: string;
}

export class AgentLinkClient {
  constructor(config: AgentLinkConfig) {
    // TODO: Implementation
    console.log('AgentLink client initialized:', config);
  }

  async createState(state: any): Promise<any> {
    // TODO: POST /states
    throw new Error('Not implemented yet');
  }

  async getState(stateId: string): Promise<any> {
    // TODO: GET /states/{id}
    throw new Error('Not implemented yet');
  }

  subscribe(callback: (state: any) => void): void {
    // TODO: WebSocket /ws
    throw new Error('Not implemented yet');
  }
}
