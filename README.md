# Mister Balance Analyzer

[![pages-build-deployment](https://github.com/AlbertSuarez/mister-balance-analyzer/actions/workflows/pages/pages-build-deployment/badge.svg)](https://github.com/AlbertSuarez/mister-balance-analyzer/actions/workflows/pages/pages-build-deployment)

[![GitHub stars](https://img.shields.io/github/stars/AlbertSuarez/mister-balance-analyzer.svg)](https://gitHub.com/AlbertSuarez/mister-balance-analyzer/stargazers/)
[![GitHub forks](https://img.shields.io/github/forks/AlbertSuarez/mister-balance-analyzer.svg)](https://gitHub.com/AlbertSuarez/mister-balance-analyzer/network/)
[![GitHub repo size in bytes](https://img.shields.io/github/repo-size/AlbertSuarez/mister-balance-analyzer.svg)](https://github.com/AlbertSuarez/mister-balance-analyzer)
[![GitHub contributors](https://img.shields.io/github/contributors/AlbertSuarez/mister-balance-analyzer.svg)](https://gitHub.com/AlbertSuarez/mister-balance-analyzer/graphs/contributors/)
[![GitHub license](https://img.shields.io/github/license/AlbertSuarez/mister-balance-analyzer.svg)](https://github.com/AlbertSuarez/mister-balance-analyzer/blob/master/LICENSE)

⚽️ Balance analyzer from Mister / BeManager

> [!NOTE]
> **🔗 Example:** [mister-balance-analyzer/data/laliga.pdf](https://asuarez.dev/mister-balance-analyzer/data/laliga.pdf)

## Summary

A Python tool that analyzes your Mister/BeManager balance history and generates comprehensive PDF reports with financial analytics, including player profitability, ROI, trading patterns, and squad investment tracking.

## Quick Start

1. Go to your [Balance Feed](https://mister.mundodeportivo.com/feed#balance) (click the balance number in the top right)
2. Save the page as HTML: `Cmd + S` (Mac) or `Ctrl + S` (Windows)
3. Run the analyzer (see [Usage](#usage))
4. Open your PDF report!

## Setup

### Requirements

- Python 3.11.3+
- [pyenv](https://github.com/pyenv/pyenv) (recommended for virtual environments)

### Installation

1. Create and activate virtual environment

   ```bash
   pyenv virtualenv 3.11.3 mister-balance-analyzer
   pyenv activate mister-balance-analyzer
   ```

2. Install dependencies

   ```bash
   pip install -r requirements.lock
   ```

### Usage

Run the analyzer with your saved HTML file:

```bash
python src/main.py --input_html data/your-balance.html --output_pdf data/your-report.pdf
```

> [!NOTE]
**Optional**: Filter by date range:

```bash
python src/main.py \
  --input_html data/your-balance.html \
  --output_pdf data/your-report.pdf \
  --date-range "2025-10-01,2025-11-01"
```

## Features

- 📊 **Player Profitability**: Track profit/loss for each player stint
- 💰 **Total Profitability**: Overall profit from sold players
- 📈 **ROI Analysis**: Return on investment for each player
- ⏱️ **Hold Time**: Average days players are held before selling
- 🏆 **Win Rate**: Percentage of profitable trades
- 👥 **Current Squad**: Investment breakdown for active players
- 🤝 **Trading Partners**: Net exchange with other managers
- 📉 **Best/Worst Deals**: Top profitable and losing trades
- 💎 **Buyout Analysis**: Highest buyout signings and sales
- 📊 **Visual Charts**: Balance timeline, transaction distribution, ROI rankings
