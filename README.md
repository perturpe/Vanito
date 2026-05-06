# Vanito

Generate a Solana wallet address that starts with any letters you choose.

**Example:** type `cat` → get an address like `catGx9oMzVsDFphe7YHmr…`

---

## Requirements

- **macOS, Windows, or Linux**
- Python 3.8 or newer

## Installation

```bash
git clone https://github.com/perturpe/Vanito.git
cd Vanito
pip3 install -r requirements.txt
```

## Usage

| Platform | Launcher |
|----------|----------|
| macOS    | Double-click `Start.command` |
| Windows  | Double-click `Start.bat` |
| Linux    | `python3 sol_vanity.py` |

Type your desired prefix (1–7 characters), hit **Generate My Wallet**, and the app searches using all your CPU cores. When a match is found:

- A system notification pops up (macOS & Linux)
- The result screen shows your **Wallet Address** and **Import Key** with one-click copy buttons
- The wallet is saved to `found_wallets.txt` in the same folder

To import into Phantom: **Settings → Import Wallet → Private Key**, then paste your Import Key.

## Security

- `found_wallets.txt` contains your real private keys. **Keep it private and never share it.**
- The app runs entirely offline. No data is sent anywhere.
- Generated keys use `libsodium` via [PyNaCl](https://pynacl.readthedocs.io/) — the same cryptographic library used by Phantom and Solana's own tooling.

## How it works

Solana addresses are derived from Ed25519 keypairs. The app spins up one worker thread per CPU core, each continuously generating random keypairs until the public key's Base58 encoding starts with your chosen prefix. Shorter prefixes (1–3 chars) finish in seconds; each extra character makes it ~58× harder.

## License

MIT
