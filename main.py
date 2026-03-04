#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SonicSupremo — CLI and client for the SonicSaver DeFi savings protocol.
Deposit ETH into pods, withdraw and claim rewards, list pods and user positions.
Guardian: register pods, set fee, pause/unpause.

SonicSaver is a time-bound savings protocol: users deposit ETH into "pods" with
a lock period and an APR (rate in basis points). After the lock expires, users
can withdraw principal plus accrued reward, or claim reward separately. A protocol
fee is taken at deposit and sent to the pulse collector. The guardian can register
pods, update caps/rates, set the fee, and pause the protocol.

Usage:
  python sonic_supremo_app.py config [--rpc-url URL] [--contract 0x...] [--save]
  python sonic_supremo_app.py deposit --rpc-url URL --private-key KEY --contract 0x... --pod-id N --amount-wei W
  python sonic_supremo_app.py withdraw --rpc-url URL --private-key KEY --contract 0x... --pod-id N --deposit-index I
  python sonic_supremo_app.py claim-reward --rpc-url URL --private-key KEY --contract 0x... --pod-id N --deposit-index I
  python sonic_supremo_app.py list-pods --rpc-url URL --contract 0x...
  python sonic_supremo_app.py user-deposits --rpc-url URL --contract 0x... --address 0x... [--pod-id N]
  python sonic_supremo_app.py protocol-stats --rpc-url URL --contract 0x...
  python sonic_supremo_app.py register-pod --rpc-url URL --private-key KEY --contract 0x... --lock-seconds S --rate-bps R --cap-wei C
  python sonic_supremo_app.py pause --rpc-url URL --private-key KEY --contract 0x...
  python sonic_supremo_app.py unpause --rpc-url URL --private-key KEY --contract 0x...
  python sonic_supremo_app.py quote --rpc-url URL --contract 0x... --amount-wei W
  python sonic_supremo_app.py simulate --rpc-url URL --contract 0x... --pod-id N --amount-wei W
  python sonic_supremo_app.py dashboard --rpc-url URL --contract 0x...
  python sonic_supremo_app.py version | constants | interactive | demo | summary | diagnostics

Config file: ~/.sonic_supremo/config.json (rpc_url, contract).
Environment: SONIC_SUPREMO_RPC_URL, SONIC_SUPREMO_CONTRACT override defaults.
Requires: web3 (pip install web3).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

APP_NAME = "SonicSupremo"
APP_VERSION = "1.0.0"
CONTRACT_NAME = "SonicSaver"
CONFIG_DIR = ".sonic_supremo"
CONFIG_FILE = "config.json"
DEFAULT_RPC_URL = os.environ.get("SONIC_SUPREMO_RPC_URL", "http://127.0.0.1:8545")
DEFAULT_CONTRACT = os.environ.get("SONIC_SUPREMO_CONTRACT", "")

# Minimal ABI for SonicSaver (state-changing + view)
SONIC_SAVER_ABI = [
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256", "name": "amountWei", "type": "uint256"}], "name": "deposit", "outputs": [], "stateMutability": "payable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256", "name": "depositIndex", "type": "uint256"}], "name": "withdraw", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256", "name": "depositIndex", "type": "uint256"}], "name": "claimReward", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256[]", "name": "depositIndices", "type": "uint256[]"}], "name": "withdrawBatch", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256[]", "name": "depositIndices", "type": "uint256[]"}], "name": "claimRewardBatch", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "lockSeconds", "type": "uint256"}, {"internalType": "uint256", "name": "rateBps", "type": "uint256"}, {"internalType": "uint256", "name": "capWei", "type": "uint256"}], "name": "registerPod", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "newFeeBps", "type": "uint256"}], "name": "setFeeBps", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "newGuardian", "type": "address"}], "name": "setGuardian", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "pause", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "unpause", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [], "name": "getProtocolStats", "outputs": [{"internalType": "uint256", "name": "totalFeesWei_", "type": "uint256"}, {"internalType": "uint256", "name": "totalDepositedWei_", "type": "uint256"}, {"internalType": "uint256", "name": "totalWithdrawnWei_", "type": "uint256"}, {"internalType": "uint256", "name": "totalRewardsPaidWei_", "type": "uint256"}, {"internalType": "uint256", "name": "reservedWei_", "type": "uint256"}, {"internalType": "uint256", "name": "podCount_", "type": "uint256"}, {"internalType": "bool", "name": "paused_", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}], "name": "getPodInfo", "outputs": [{"internalType": "uint256", "name": "lockSeconds", "type": "uint256"}, {"internalType": "uint256", "name": "rateBps", "type": "uint256"}, {"internalType": "uint256", "name": "capWei", "type": "uint256"}, {"internalType": "uint256", "name": "totalDeposited", "type": "uint256"}, {"internalType": "bool", "name": "active", "type": "bool"}, {"internalType": "uint256", "name": "createdAtBlock", "type": "uint256"}, {"internalType": "bytes32", "name": "nameHash", "type": "bytes32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "address", "name": "user", "type": "address"}], "name": "getUserDepositCount", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "address", "name": "user", "type": "address"}, {"internalType": "uint256", "name": "index", "type": "uint256"}], "name": "getUserDeposit", "outputs": [{"internalType": "uint256", "name": "principalWei", "type": "uint256"}, {"internalType": "uint256", "name": "unlockAt", "type": "uint256"}, {"internalType": "uint256", "name": "accruedRewardAtLock", "type": "uint256"}, {"internalType": "uint256", "name": "rateBpsAtDeposit", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "address", "name": "user", "type": "address"}, {"internalType": "uint256", "name": "depositIndex", "type": "uint256"}], "name": "getRewardForDeposit", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getNextPodId", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getDashboardSnapshot", "outputs": [{"internalType": "uint256", "name": "totalFees", "type": "uint256"}, {"internalType": "uint256", "name": "totalDeposited", "type": "uint256"}, {"internalType": "uint256", "name": "totalWithdrawn", "type": "uint256"}, {"internalType": "uint256", "name": "totalRewardsPaid", "type": "uint256"}, {"internalType": "uint256", "name": "reserved", "type": "uint256"}, {"internalType": "uint256", "name": "contractBalance", "type": "uint256"}, {"internalType": "uint256", "name": "podCount", "type": "uint256"}, {"internalType": "bool", "name": "isPaused", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "amountWei", "type": "uint256"}], "name": "quoteDeposit", "outputs": [{"internalType": "uint256", "name": "feeWei", "type": "uint256"}, {"internalType": "uint256", "name": "netWei", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256", "name": "amountWei", "type": "uint256"}], "name": "simulateDeposit", "outputs": [{"internalType": "uint256", "name": "netWei", "type": "uint256"}, {"internalType": "uint256", "name": "unlockAt", "type": "uint256"}, {"internalType": "uint256", "name": "projectedRewardWei", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "fromId", "type": "uint256"}, {"internalType": "uint256", "name": "count", "type": "uint256"}], "name": "getPodsBatch", "outputs": [{"internalType": "uint256[]", "name": "ids", "type": "uint256[]"}, {"internalType": "uint256[]", "name": "lockSecondsArr", "type": "uint256[]"}, {"internalType": "uint256[]", "name": "rateBpsArr", "type": "uint256[]"}, {"internalType": "uint256[]", "name": "capWeiArr", "type": "uint256[]"}, {"internalType": "uint256[]", "name": "totalDepositedArr", "type": "uint256[]"}, {"internalType": "bool[]", "name": "activeArr", "type": "bool[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "user", "type": "address"}], "name": "getPodsWhereUserHasDeposits", "outputs": [{"internalType": "uint256[]", "name": "podIds", "type": "uint256[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "address", "name": "user", "type": "address"}], "name": "getDepositSummaryForUser", "outputs": [{"internalType": "uint256", "name": "totalPrincipal", "type": "uint256"}, {"internalType": "uint256", "name": "totalClaimableReward", "type": "uint256"}, {"internalType": "uint256", "name": "depositCount", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "protocolPaused", "outputs": [{"internalType": "bool", "name": "", "type": "bool"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "feeBps", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "BPS_DENOM", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "MAX_FEE_BPS", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "MIN_LOCK_SECONDS", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "MAX_LOCK_SECONDS", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "SECONDS_PER_YEAR", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}], "name": "getCapacityRemaining", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "address", "name": "user", "type": "address"}], "name": "getDepositIndicesUnlocked", "outputs": [{"internalType": "uint256[]", "name": "indices", "type": "uint256[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "address", "name": "user", "type": "address"}], "name": "getTotalWithdrawableForUserInPod", "outputs": [{"internalType": "uint256", "name": "totalPrincipal", "type": "uint256"}, {"internalType": "uint256", "name": "totalReward", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getProtocolHealth", "outputs": [{"internalType": "bool", "name": "balanceOk", "type": "bool"}, {"internalType": "uint256", "name": "balanceWei", "type": "uint256"}, {"internalType": "uint256", "name": "reservedWei", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "uint256", "name": "podId", "type": "uint256"}, {"internalType": "uint256", "name": "amountWei", "type": "uint256"}], "name": "validateDepositParams", "outputs": [{"internalType": "bool", "name": "valid", "type": "bool"}, {"internalType": "string", "name": "err", "type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getAvailablePodIds", "outputs": [{"internalType": "uint256[]", "name": "ids", "type": "uint256[]"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "user", "type": "address"}], "name": "getUserGlobalPrincipal", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"internalType": "address", "name": "user", "type": "address"}], "name": "getUserGlobalClaimableReward", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
]

# -----------------------------------------------------------------------------
# Local reward calculation (mirrors contract formula)
# -----------------------------------------------------------------------------

BPS_DENOM_LOCAL = 10_000
SECONDS_PER_YEAR_LOCAL = 365 * 24 * 3600

def compute_reward_wei(principal_wei: int, rate_bps: int, elapsed_seconds: int, accrued_wei: int = 0) -> int:
    """Reward = principal * rateBps * elapsed / (BPS_DENOM * SECONDS_PER_YEAR) - accrued."""
    if principal_wei == 0 or elapsed_seconds <= 0:
        return 0
    full = (principal_wei * rate_bps * elapsed_seconds) // (BPS_DENOM_LOCAL * SECONDS_PER_YEAR_LOCAL)
    if full <= accrued_wei:
        return 0
    return full - accrued_wei

def compute_fee_wei(amount_wei: int, fee_bps: int) -> int:
    return (amount_wei * fee_bps) // BPS_DENOM_LOCAL

def compute_net_after_fee(amount_wei: int, fee_bps: int) -> int:
    return amount_wei - compute_fee_wei(amount_wei, fee_bps)

def project_reward_at_unlock(principal_wei: int, rate_bps: int, lock_seconds: int) -> int:
    """Projected reward if principal is locked for lock_seconds at rate_bps (full period)."""
    return (principal_wei * rate_bps * lock_seconds) // (BPS_DENOM_LOCAL * SECONDS_PER_YEAR_LOCAL)

def local_quote_deposit(amount_wei: int, fee_bps: int) -> Tuple[int, int]:
    """Local quote: (fee_wei, net_wei) for a deposit. Matches contract quoteDeposit."""
    fee = compute_fee_wei(amount_wei, fee_bps)
    return (fee, amount_wei - fee)

def local_simulate_deposit(amount_wei: int, fee_bps: int, lock_seconds: int, rate_bps: int) -> Tuple[int, int, int]:
    """Local simulation: (net_wei, projected_reward_wei). unlock_at not computed (needs block.timestamp)."""
    net = compute_net_after_fee(amount_wei, fee_bps)
    proj = project_reward_at_unlock(net, rate_bps, lock_seconds)
    return (net, proj, 0)

def check_capacity(contract, pod_id: int, amount_wei: int) -> bool:
    """Return True if pod has at least amount_wei capacity remaining."""
    try:
        rem = contract.functions.getCapacityRemaining(pod_id).call()
        return rem >= amount_wei
    except Exception:
        return False

def get_user_pod_ids(contract, user_address: str) -> List[int]:
    """Return list of pod ids where user has at least one deposit."""
    try:
        return list(contract.functions.getPodsWhereUserHasDeposits(user_address).call())
    except Exception:
        return []

def build_user_report_dict(contract, user_address: str) -> dict:
    """Build a dict with user's total principal, claimable reward, and per-pod breakdown."""
    pod_ids = get_user_pod_ids(contract, user_address)
    total_principal = 0
    total_claimable = 0
    pods = []
    for pid in pod_ids:
        princ, claimable, count = contract.functions.getDepositSummaryForUser(pid, user_address).call()
        total_principal += princ
        total_claimable += claimable
        pods.append({"pod_id": pid, "principal_wei": princ, "claimable_reward_wei": claimable, "deposit_count": count})
    return {
        "address": user_address,
        "total_principal_wei": total_principal,
        "total_claimable_reward_wei": total_claimable,
        "pods": pods,
    }

def format_user_report(report: dict) -> str:
    """Format build_user_report_dict output as multiline string."""
    lines = [
        f"Address: {report['address']}",
        f"Total principal: {format_wei(report['total_principal_wei'])}",
        f"Total claimable reward: {format_wei(report['total_claimable_reward_wei'])}",
        "Per-pod:",
    ]
    for p in report["pods"]:
        lines.append(f"  Pod #{p['pod_id']}: principal={format_wei(p['principal_wei'])}  claimable={format_wei(p['claimable_reward_wei'])}  deposits={p['deposit_count']}")
    return "\n".join(lines)

# -----------------------------------------------------------------------------
# Extended validation and eligibility helpers
# -----------------------------------------------------------------------------

def validate_pod_id_range(pod_id: int, next_pod_id: int) -> bool:
    """Return True if pod_id is in valid range [1, next_pod_id - 1]."""
    return 1 <= pod_id < next_pod_id

def validate_amount_positive(amount_wei: int) -> bool:
    return amount_wei > 0

def validate_fee_bps(fee_bps: int, max_fee_bps: int = 500) -> bool:
    return 0 <= fee_bps <= max_fee_bps

def validate_lock_seconds(lock_seconds: int, min_sec: int = 7 * 86400, max_sec: int = 730 * 86400) -> bool:
    return min_sec <= lock_seconds <= max_sec

def validate_rate_bps(rate_bps: int, max_rate_bps: int = 2000) -> bool:
    return 0 <= rate_bps <= max_rate_bps

def eligibility_deposit(contract, pod_id: int, amount_wei: int) -> Tuple[bool, str]:
    """Check if a deposit would be accepted. Returns (ok, message)."""
    try:
        valid, err = contract.functions.validateDepositParams(pod_id, amount_wei).call()
        if valid:
            return (True, "OK")
        return (False, err or "Unknown")
    except Exception as e:
        return (False, str(e))

def print_eligibility(contract, pod_id: int, amount_wei: int) -> None:
    """Print eligibility result for a deposit."""
    ok, msg = eligibility_deposit(contract, pod_id, amount_wei)
    if ok:
        print("Eligible: deposit would succeed (subject to sender balance and gas).")
    else:
        print("Not eligible:", msg)

# -----------------------------------------------------------------------------
# Command: check-eligibility
# -----------------------------------------------------------------------------

def cmd_check_eligibility(args: argparse.Namespace) -> int:
    rpc = args.rpc_url or load_config().get("rpc_url", DEFAULT_RPC_URL)
    contract_addr = args.contract or load_config().get("contract", DEFAULT_CONTRACT)
    pod_id = getattr(args, "pod_id", None)
    amount_wei = getattr(args, "amount_wei", None)
    if not contract_addr or pod_id is None or amount_wei is None:
        print("Error: --contract, --pod-id, --amount-wei required", file=sys.stderr)
        return 1
    try:
        pod_id = int(pod_id)
        amount_wei = parse_wei(str(amount_wei))
        w3 = get_w3(rpc)
        contract = get_contract(w3, contract_addr)
        print_eligibility(contract, pod_id, amount_wei)
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1
    return 0

# -----------------------------------------------------------------------------
# Help-all: print all commands with one-line descriptions
# -----------------------------------------------------------------------------

COMMAND_HELP_ALL = """
config             Show or save RPC URL and contract address.
deposit            Deposit ETH into a pod (payable).
withdraw           Withdraw one deposit after unlock (principal + reward).
claim-reward       Claim reward for one unlocked deposit.
withdraw-batch     Withdraw multiple deposits in one transaction.
claim-reward-batch Claim rewards for multiple deposits.
list-pods          List all registered pods with lock, rate, cap, deposited.
user-deposits      List deposits for an address (optionally filter by pod).
user-global-stats  Total principal and claimable reward across all pods for an address.
user-report        Structured report for one address (principal, claimable, per-pod).
export-report      Export user report as JSON to a file.
protocol-stats     Protocol-level totals (fees, deposited, withdrawn, rewards, reserved).
protocol-health    Contract balance vs reserved (health check).
dashboard          Single-call snapshot: fees, deposited, withdrawn, reserved, balance, pods, paused.
summary            Dashboard + health + pods in one output.
available-pods     Pod IDs that are active and have capacity remaining.
pod-info           Detailed info for one pod (lock, rate, cap, deposited, active, created block).
validate-deposit   Check if deposit(podId, amountWei) would succeed.
check-eligibility  Alias-style check for deposit eligibility.
withdrawable       List withdrawable (unlocked) positions for an address.
register-pod       [Guardian] Register a new pod (lock seconds, rate bps, cap wei).
set-fee            [Guardian] Set protocol fee in basis points.
set-guardian       [Guardian] Set new guardian address.
pause              [Guardian] Pause protocol (no new deposits).
unpause            [Guardian] Unpause protocol.
quote              Quote fee and net principal for a deposit amount.
simulate           Simulate deposit: net principal, unlock time, projected reward.
gas-estimate       Estimate gas for deposit, withdraw, or claim-reward.
constants          Show contract constants (BPS_DENOM, MAX_FEE_BPS, lock limits, feeBps).
diagnostics        Run many view calls and print results (for support/debug).
demo               Print usage examples.
version            Show app version and contract name.
interactive        Print interactive mode hints.
"""

def cmd_help_all(args: argparse.Namespace) -> int:
    print("SonicSupremo commands:")
    print(COMMAND_HELP_ALL)
    return 0

# -----------------------------------------------------------------------------
# Contract events reference (for log parsing / indexers)
# -----------------------------------------------------------------------------

SONIC_SAVER_EVENTS = [
    "PodRegistered(podId,lockSeconds,rateBps,capWei)",
    "DepositPlaced(user,podId,amountWei,unlockAt)",
    "WithdrawalExecuted(user,podId,principalWei,rewardWei)",
    "RewardClaimed(user,podId,amountWei)",
    "FeeHarvested(collector,amountWei)",
    "GuardianSet(previousGuardian,newGuardian)",
    "ProtocolPaused(atBlock)",
    "ProtocolUnpaused(atBlock)",
    "PodCapUpdated(podId,previousCap,newCapWei)",
    "RateUpdated(podId,previousRateBps,newRateBps)",
    "EmergencySweep(tokenOrZero,amountWei)",
]

def get_contract_events_help() -> str:
    return "SonicSaver events:\n" + "\n".join("  " + e for e in SONIC_SAVER_EVENTS)

def cmd_events_help(args: argparse.Namespace) -> int:
    print(get_contract_events_help())
    return 0

# -----------------------------------------------------------------------------
# Default pod presets (for quick register-pod examples)
# -----------------------------------------------------------------------------

POD_PRESETS = {
    "30d_5pct_100eth": {"lock_seconds": 30 * 86400, "rate_bps": 500, "cap_wei": 100 * 10**18},
    "90d_7pct_500eth": {"lock_seconds": 90 * 86400, "rate_bps": 700, "cap_wei": 500 * 10**18},
    "180d_10pct_1000eth": {"lock_seconds": 180 * 86400, "rate_bps": 1000, "cap_wei": 1000 * 10**18},
    "365d_12pct_2000eth": {"lock_seconds": 365 * 86400, "rate_bps": 1200, "cap_wei": 2000 * 10**18},
}

def get_preset(name: str) -> Optional[dict]:
    return POD_PRESETS.get(name)

def cmd_presets(args: argparse.Namespace) -> int:
    print("Pod presets (for register-pod):")
    for name, p in POD_PRESETS.items():
        print(f"  {name}: lock={format_seconds(p['lock_seconds'])}  rate={format_bps(p['rate_bps'])}  cap={format_wei(p['cap_wei'])}")
    return 0

# -----------------------------------------------------------------------------
# Chain ID helper (for signing)
# -----------------------------------------------------------------------------

def get_chain_id(w3) -> int:
    try:
        return w3.eth.chain_id
    except Exception:
        return 0

def cmd_chain_id(args: argparse.Namespace) -> int:
    rpc = args.rpc_url or load_config().get("rpc_url", DEFAULT_RPC_URL)
    try:
        w3 = get_w3(rpc)
        cid = get_chain_id(w3)
