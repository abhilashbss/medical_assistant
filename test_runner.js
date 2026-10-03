#!/usr/bin/env node
// Test runner that translates npm/Jest-style args to pytest args and captures evidence

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);

// Convert --grep to pytest -k flag.
// When the grep mentions "functional", target the dedicated functional test
// file; otherwise default to the unit test file.
let pytestArgs = ['tests/test_medication_tracker.py', '-v', '--tb=short'];
let grepPattern = null;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--grep' && i + 1 < args.length) {
    grepPattern = args[i + 1];
    // 'functional.*medicine-tracker' targets the functional suite.
    if (/functional/i.test(grepPattern)) {
      pytestArgs[0] = 'tests/functional/test_medicine_tracker.py';
    }
    // Convert regex pattern to pytest keyword expression
    // 'functional.*medicine-tracker' -> 'functional and medicine and tracker'
    // Split on regex metacharacters and combine with 'and'
    const parts = grepPattern.split(/[.\-*]+/).filter(p => p.length > 0);
    if (parts.length > 0) {
      pytestArgs.push('-k', parts.join(' and '));
    }
    i++; // Skip the grep value
  } else if (args[i] !== '--grep') {
    // Pass through other args if they're not --grep
    pytestArgs.push(args[i]);
  }
}

// Capture output to file for evidence
const evidenceDir = path.join(__dirname, '.see', 'e2e-artifacts');
if (!fs.existsSync(evidenceDir)) {
  fs.mkdirSync(evidenceDir, { recursive: true });
}

// Resolve a Python interpreter: prefer a local venv, fall back to PATH.
const venvPython = path.join(__dirname, '.venv', 'bin', 'python');
const pythonBin = fs.existsSync(venvPython) ? venvPython : 'python3';

const result = spawnSync(pythonBin, ['-m', 'pytest', ...pytestArgs], {
  encoding: 'utf-8',
  stdio: ['inherit', 'pipe', 'pipe']
});

// Write combined output to transcript
const transcript = [
  '=== MEDICATION TRACKER FUNCTIONAL TEST TRANSCRIPT ===',
  `Command: npm test -- --grep '${grepPattern || ''}'`,
  `Date: ${new Date().toISOString()}`,
  '',
  '--- STDOUT ---',
  result.stdout || '',
  '',
  '--- STDERR ---',
  result.stderr || '',
  '',
  '--- RESULT ---',
  `Exit Code: ${result.status}`,
  result.status === 0 ? 'STATUS: ALL FUNCTIONAL TESTS PASSED' : 'STATUS: TESTS FAILED',
  '',
  '=== END TRANSCRIPT ==='
].join('\n');

const transcriptPath = path.join(evidenceDir, 'console-transcript.txt');
fs.writeFileSync(transcriptPath, transcript);

// Also write stdout only for cleaner viewing
fs.writeFileSync(path.join(evidenceDir, 'test-output.txt'), result.stdout || '');

// Print to console
process.stdout.write(result.stdout || '');
if (result.stderr) {
  process.stderr.write(result.stderr);
}

process.exit(result.status || 0);
