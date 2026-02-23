#!/usr/bin/env node
/**
 * AgentLink OpenClaw Plugin CLI
 * 
 * Usage: agentlink <command> [options]
 */

const fs = require('fs');
const path = require('path');

// Load configuration
const configPath = path.join(__dirname, 'config.json');
const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

// Import AgentLink client from node_modules

const { AgentLinkClient } = require('@agentlink/client');

// Parse command line arguments
const args = process.argv.slice(2);
const command = args[0];

// Get agent ID from config or environment
function getAgentId() {
  if (config.agentId === 'auto') {
    // Try to get from OpenClaw environment
    return process.env.OPENCLAW_AGENT || process.env.AGENT_ID || 'default-agent';
  }
  return config.agentId;
}

// Initialize client
const client = new AgentLinkClient({
  url: config.url,
  agentId: getAgentId()
});

// Format helpers
function formatState(state) {
  const { id, agent_id, task, handoff } = state;
  let output = `✅ State: ${id.slice(0, 8)}...\n`;
  output += `Agent: ${agent_id} | Type: ${task.type} | Priority: ${task.priority}\n`;
  output += `Task: ${task.description}\n`;
  if (task.status) output += `Status: ${task.status}\n`;
  if (handoff?.to_agent) {
    output += `→ Handoff to: ${handoff.to_agent} (${handoff.reason})\n`;
    if (handoff.required_skills?.length > 0) {
      output += `  Skills: ${handoff.required_skills.join(', ')}\n`;
    }
  }
  return output;
}

function formatStateList(states) {
  if (states.length === 0) {
    return '📭 No states found';
  }
  let output = `📊 Found ${states.length} state(s):\n\n`;
  states.forEach((state, i) => {
    output += `${i + 1}. ${formatState(state)}\n`;
  });
  return output;
}

// Parse options from command line
function parseOptions(args) {
  const options = {};
  const positional = [];
  
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg.startsWith('--')) {
      const key = arg.slice(2);
      const value = args[i + 1];
      if (!value || value.startsWith('--')) {
        options[key] = true;
      } else {
        if (options[key]) {
          if (!Array.isArray(options[key])) {
            options[key] = [options[key]];
          }
          options[key].push(value);
        } else {
          options[key] = value;
        }
        i++;
      }
    } else {
      positional.push(arg);
    }
  }
  
  return { options, positional };
}

// Command implementations
async function createState(parsed) {
  const { options } = parsed;
  
  if (!options.type || !options.description) {
    console.error('Error: --type and --description required');
    console.error('Usage: agentlink create-state --type <type> --description "..." [options]');
    process.exit(1);
  }
  
  const state = {
    task: {
      type: options.type,
      description: options.description,
      priority: parseInt(options.priority || '3'),
      status: options.status || 'pending'
    },
    context: {
      files: [],
      git: null,
      errors: []
    },
    knowledge: {
      amem_ids: options['amem-id'] ? (Array.isArray(options['amem-id']) ? options['amem-id'] : [options['amem-id']]) : [],
      qmd_refs: options['qmd-ref'] ? (Array.isArray(options['qmd-ref']) ? options['qmd-ref'] : [options['qmd-ref']]) : [],
      external_urls: options.url ? (Array.isArray(options.url) ? options.url : [options.url]) : []
    },
    working_memory: {
      hypotheses: options.hypothesis ? (Array.isArray(options.hypothesis) ? options.hypothesis : [options.hypothesis]) : [],
      open_questions: options.question ? (Array.isArray(options.question) ? options.question : [options.question]) : [],
      decisions: [],
      findings: options.finding ? (Array.isArray(options.finding) ? options.finding : [options.finding]) : []
    },
    handoff: null
  };
  
  // Add files
  if (options.file) {
    const files = Array.isArray(options.file) ? options.file : [options.file];
    state.context.files = files.map(f => ({ path: f }));
  }
  
  // Add git info
  if (options['git-commit']) {
    state.context.git = {
      repo: options['git-repo'] || 'agentlink',
      branch: options['git-branch'] || 'main',
      commit: options['git-commit']
    };
  }
  
  // Add decisions
  if (options.decision) {
    const decisions = Array.isArray(options.decision) ? options.decision : [options.decision];
    const reasons = options.reason ? (Array.isArray(options.reason) ? options.reason : [options.reason]) : [];
    
    decisions.forEach((what, i) => {
      state.working_memory.decisions.push({
        what,
        why: reasons[i] || 'Not specified',
        when: new Date().toISOString()
      });
    });
  }
  
  // Add handoff
  if (options.handoff) {
    state.handoff = {
      to_agent: options.handoff,
      reason: options['handoff-reason'] || 'Handoff requested',
      required_skills: options.skill ? (Array.isArray(options.skill) ? options.skill : [options.skill]) : []
    };
  }
  
  const result = await client.createState(state);
  console.log(formatState(result));
}

async function getState(parsed) {
  const { positional } = parsed;
  
  if (!positional[1]) {
    console.error('Error: state ID required');
    console.error('Usage: agentlink get-state <state-id>');
    process.exit(1);
  }
  
  const state = await client.getState(positional[1]);
  console.log(formatState(state));
}

async function listStates(parsed) {
  const { options } = parsed;
  
  const filter = {};
  if (options['agent-id']) filter.agent_id = options['agent-id'];
  if (options.status) filter.status = options.status;
  if (options.limit) filter.limit = parseInt(options.limit);
  
  const states = await client.listStates(filter);
  console.log(formatStateList(states));
}

async function createHandoff(parsed) {
  const { positional, options } = parsed;
  
  if (!positional[1]) {
    console.error('Error: target agent ID required');
    console.error('Usage: agentlink handoff <agent-id> --reason "..." [--skill ...]');
    process.exit(1);
  }
  
  // Create minimal handoff state
  const state = {
    task: {
      type: 'review',
      description: options.description || 'Handoff from ' + getAgentId(),
      priority: parseInt(options.priority || '3'),
      status: 'pending'
    },
    context: {},
    handoff: {
      to_agent: positional[1],
      reason: options.reason || 'Handoff requested',
      required_skills: options.skill ? (Array.isArray(options.skill) ? options.skill : [options.skill]) : []
    }
  };
  
  const result = await client.createState(state);
  console.log(formatState(result));
}

async function checkHealth() {
  const health = await client.health();
  console.log(JSON.stringify(health, null, 2));
}

function showHelp() {
  console.log(`
AgentLink OpenClaw Plugin

Usage: agentlink <command> [options]

Commands:
  create-state     Create a new agent state
  get-state <id>   Retrieve a state by ID
  list-states      List all states (optionally filtered)
  handoff <agent>  Create handoff to another agent
  health           Check backend health

Examples:
  agentlink create-state --type bug_fix --description "Fixed bug" --priority 5
  agentlink get-state 1b96224e-e303-4d6c-a99e-2d58c1b51ad6
  agentlink list-states --agent-id castiel
  agentlink handoff lilith --reason "Architecture review"
  agentlink health

For detailed usage, see SKILL.md
`);
}

// Main command router
async function main() {
  try {
    const parsed = parseOptions(args);
    
    switch (command) {
      case 'create-state':
        await createState(parsed);
        break;
      case 'get-state':
        await getState(parsed);
        break;
      case 'list-states':
        await listStates(parsed);
        break;
      case 'handoff':
        await createHandoff(parsed);
        break;
      case 'health':
        await checkHealth();
        break;
      case '--help':
      case '-h':
      case 'help':
      default:
        showHelp();
        break;
    }
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
}

main();
