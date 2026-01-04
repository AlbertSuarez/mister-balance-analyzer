import argparse
import re
from collections import defaultdict
from datetime import datetime, timezone

from bs4 import BeautifulSoup


def parse_args():
    parser = argparse.ArgumentParser(description='Mister Balance Analyzer')
    parser.add_argument('--input_html', type=str, required=True, help='Input HTMLfile')
    parser.add_argument('--output_pdf', type=str, required=True, help='Output PDF file')
    parser.add_argument('--print_top_n', type=int, required=False, default=20, help='Print top N players')
    args = parser.parse_args()
    return args


def __parse_transaction_type(type_str):
    type_map = {
        'Bonificación': 'bonuses',  # Bonuses/rewards received from the game
        'Buyout sale': 'buyout_sale',  # Selling a player via their buyout clause
        'Buyout signing': 'buyout_signing',  # Buying a player via their buyout clause
        'Loan purchase': 'loan_purchase',  # Acquiring a player on loan
        'Loan sale': 'loan_sale',  # Loaning out a player to another team
        'Penalización': 'clause_increase',  # Player's clause increased
        'Purchase': 'purchase',  # Regular player purchases from the market
        'Sale': 'sale',  # Regular player sales to the market
    }
    return type_map.get(type_str, type_str)


def __parse_reason(reason):
    # Parse reason field to extract footballer and league player
    footballer = None
    league_player_associated = None
    # Pattern: "Footballer to League Player" (buyout_sale, buyout_signing, loan_purchase, loan_sale, purchase, sale)
    if ' to ' in reason:
        parts = reason.split(' to ')
        if len(parts) == 2:
            footballer = parts[0].strip()
            league_player_associated = parts[1].strip() if parts[1].strip() != 'Mister' else None
    # Pattern: "Modificación de cláusula (X%) de Footballer" (clause_increase)
    elif 'Modificación de cláusula' in reason:
        # Split on the last occurrence of ' de '
        last_de_idx = reason.rfind(' de ')
        if last_de_idx != -1:
            footballer = reason[last_de_idx + 4 :].strip()
    # Pattern: "Jornada X" (bonuses) - no footballer or league player
    return footballer, league_player_associated


def _parse_html(input_html):
    # Read the HTML content
    with open(input_html, 'r', encoding='utf-8') as f:
        html_content = f.read()
    # Parse the HTML content
    soup = BeautifulSoup(html_content, 'html.parser')
    # Find the balance history section
    balance_history = soup.find('ul', class_='balance-history')
    if not balance_history:
        print('No balance history found')
        return []
    # Find all transaction items (li elements)
    transactions = []
    for item in balance_history.find_all('li'):
        left_div = item.find('div', class_='left')
        right_div = item.find('div', class_='right')
        if not left_div or not right_div:
            continue
        # Extract transaction type
        type_div = left_div.find('div', class_='type')
        transaction_type_raw = type_div.get_text(strip=True) if type_div else ''
        transaction_type = __parse_transaction_type(transaction_type_raw)
        # Extract reason/description and parse to extract footballer and league player
        reason_div = left_div.find('div', class_='reason')
        reason = reason_div.get_text(strip=True, separator=' ') if reason_div else ''
        footballer, league_player_associated = __parse_reason(reason)
        # Extract date and convert to UTC datetime
        date_div = left_div.find('div', class_='date')
        date_full_str = date_div.get('title', '') if date_div else ''
        date_full = None
        if date_full_str:
            try:
                # Parse format: "04/01/2026 – 14:41"
                date_full = datetime.strptime(date_full_str, '%d/%m/%Y – %H:%M').replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        # Extract amount
        amount_div = right_div.find('div', class_='amount')
        amount_text = amount_div.get_text(strip=True) if amount_div else ''
        # Parse amount (remove commas and convert to number)
        amount_clean = re.sub(r'[,\s]', '', amount_text)
        try:
            amount = int(amount_clean)
        except ValueError:
            amount = 0
        # Extract balance after transaction
        balance_small = right_div.find('small')
        balance_text = balance_small.get_text(strip=True) if balance_small else ''
        balance_clean = re.sub(r'[,\s]', '', balance_text)
        try:
            balance_after = int(balance_clean)
        except ValueError:
            balance_after = 0
        # Add transaction to list
        transactions.append(
            {
                'type': transaction_type,
                'footballer': footballer,
                'league_player_associated': league_player_associated,
                'date_full': date_full,
                'amount': amount,
                'balance_after': balance_after,
            }
        )
    # Return the transactions
    return transactions


def _analyze(transactions):
    analytics = {}

    # 1. Player profitability analysis
    player_transactions = defaultdict(lambda: {'purchases': [], 'sales': [], 'clause_increases': []})
    for t in transactions:
        if t['footballer']:
            if t['type'] in ['purchase', 'buyout_signing', 'loan_purchase']:
                player_transactions[t['footballer']]['purchases'].append(t)
            elif t['type'] in ['sale', 'buyout_sale', 'loan_sale']:
                player_transactions[t['footballer']]['sales'].append(t)
            elif t['type'] == 'clause_increase':
                player_transactions[t['footballer']]['clause_increases'].append(t)
    # Calculate profitability for each player
    player_profitability = []
    for player, data in player_transactions.items():
        total_spent = sum(abs(t['amount']) for t in data['purchases'])
        total_spent += sum(abs(t['amount']) for t in data['clause_increases'])
        total_earned = sum(t['amount'] for t in data['sales'])
        net_profit = total_earned - total_spent
        # Only include players who have been sold AND were actually purchased (not initial free squad)
        if data['sales'] and data['purchases']:
            player_profitability.append(
                {
                    'player': player,
                    'total_spent': total_spent,
                    'total_earned': total_earned,
                    'net_profit': net_profit,
                    'num_purchases': len(data['purchases']),
                    'num_sales': len(data['sales']),
                    'num_clause_increases': len(data['clause_increases']),
                }
            )
    # Sort by profitability
    player_profitability.sort(key=lambda x: x['net_profit'], reverse=True)
    analytics['player_profitability'] = player_profitability

    # 2. Total profitability (players no longer in team)
    total_profitability = sum(p['net_profit'] for p in player_profitability)
    analytics['total_profitability'] = total_profitability

    # 3. Ranking of buyouts (most expensive buyout signings and sales)
    buyout_signings = [t for t in transactions if t['type'] == 'buyout_signing']
    buyout_signings.sort(key=lambda x: abs(x['amount']), reverse=True)
    analytics['top_buyout_signings'] = buyout_signings
    buyout_sales = [t for t in transactions if t['type'] == 'buyout_sale']
    buyout_sales.sort(key=lambda x: x['amount'], reverse=True)
    analytics['top_buyout_sales'] = buyout_sales

    # 4. Transaction type breakdown
    type_summary = defaultdict(lambda: {'count': 0, 'total_amount': 0, 'avg_amount': 0})
    for t in transactions:
        type_summary[t['type']]['count'] += 1
        type_summary[t['type']]['total_amount'] += t['amount']
    for trans_type in type_summary:
        count = type_summary[trans_type]['count']
        type_summary[trans_type]['avg_amount'] = type_summary[trans_type]['total_amount'] / count if count > 0 else 0
    analytics['type_summary'] = dict(type_summary)

    # 5. Most active trading partners (league players)
    trading_partners = defaultdict(lambda: {'purchases': 0, 'sales': 0, 'spent': 0, 'earned': 0, 'net_exchange': 0})
    for t in transactions:
        if t['league_player_associated']:
            partner = t['league_player_associated']
            if t['type'] in ['buyout_signing', 'loan_purchase']:
                trading_partners[partner]['purchases'] += 1
                trading_partners[partner]['spent'] += abs(t['amount'])
            elif t['type'] in ['buyout_sale', 'loan_sale']:
                trading_partners[partner]['sales'] += 1
                trading_partners[partner]['earned'] += t['amount']
    # Calculate net exchange for each partner
    for partner in trading_partners:
        trading_partners[partner]['net_exchange'] = (
            trading_partners[partner]['earned'] - trading_partners[partner]['spent']
        )
    top_partners = sorted(
        [{'partner': k, **v} for k, v in trading_partners.items()], key=lambda x: x['net_exchange'], reverse=True
    )
    analytics['top_trading_partners'] = top_partners

    # 6. Most expensive mistakes (players bought and sold at a loss)
    biggest_losses = [p for p in player_profitability if p['net_profit'] < 0]
    biggest_losses.sort(key=lambda x: x['net_profit'])
    analytics['biggest_losses'] = biggest_losses

    # 7. Best deals (highest profit players)
    best_deals = [p for p in player_profitability if p['net_profit'] > 0]
    best_deals.sort(key=lambda x: x['net_profit'], reverse=True)
    analytics['best_deals'] = best_deals

    # 8. Clause increase analysis
    clause_increases = [t for t in transactions if t['type'] == 'clause_increase']
    total_clause_cost = sum(abs(t['amount']) for t in clause_increases)
    analytics['clause_increase_summary'] = {
        'total_count': len(clause_increases),
        'total_cost': total_clause_cost,
        'avg_cost': total_clause_cost / len(clause_increases) if clause_increases else 0,
    }

    # 9. Current squad value (players purchased but not sold, or initial squad with clause increases)
    current_squad = []
    for player, data in player_transactions.items():
        # Include players who haven't been sold AND either were purchased OR have clause increases
        if not data['sales'] and (data['purchases'] or data['clause_increases']):
            total_invested = sum(abs(t['amount']) for t in data['purchases'])
            total_invested += sum(abs(t['amount']) for t in data['clause_increases'])
            current_squad.append(
                {
                    'player': player,
                    'total_invested': total_invested,
                    'num_purchases': len(data['purchases']),
                    'num_clause_increases': len(data['clause_increases']),
                }
            )
    current_squad.sort(key=lambda x: x['total_invested'], reverse=True)
    analytics['current_squad'] = current_squad
    analytics['current_squad_total_investment'] = sum(p['total_invested'] for p in current_squad)

    return analytics


def _print_analytics(analytics, print_top_n):
    # Print analytics
    print('\n' + '=' * 70)
    print('MISTER BALANCE ANALYTICS')
    print('=' * 70)

    # Total profitability
    print(f'\n📊 TOTAL PROFITABILITY (Sold Players): {analytics["total_profitability"]:,}')

    # Transaction type summary
    print('\n📈 TRANSACTION TYPE BREAKDOWN:')
    for trans_type, summary in sorted(analytics['type_summary'].items()):
        print(f'  {trans_type}:')
        print(f'    Count: {summary["count"]}')
        print(f'    Total: {summary["total_amount"]:,}')
        print(f'    Average: {summary["avg_amount"]:,.0f}')

    # Best deals
    print(f'\n💰 TOP {print_top_n} BEST DEALS (Highest Profit):')
    for i, player in enumerate(analytics['best_deals'][:print_top_n], 1):
        print(f'  {i}. {player["player"]}: +{player["net_profit"]:,}')
        print(f'     Spent: {player["total_spent"]:,} | Earned: {player["total_earned"]:,}')

    # Biggest losses
    print(f'\n📉 TOP {print_top_n} BIGGEST LOSSES:')
    for i, player in enumerate(analytics['biggest_losses'][:print_top_n], 1):
        print(f'  {i}. {player["player"]}: {player["net_profit"]:,}')
        print(f'     Spent: {player["total_spent"]:,} | Earned: {player["total_earned"]:,}')

    # Top buyout signings
    print(f'\n🔥 TOP {print_top_n} MOST EXPENSIVE BUYOUT SIGNINGS:')
    for i, t in enumerate(analytics['top_buyout_signings'][:print_top_n], 1):
        print(f'  {i}. {t["footballer"]}: {t["amount"]:,}')
        if t['league_player_associated']:
            print(f'     From: {t["league_player_associated"]}')

    # Top buyout sales
    print(f'\n💸 TOP {print_top_n} HIGHEST BUYOUT SALES:')
    for i, t in enumerate(analytics['top_buyout_sales'][:print_top_n], 1):
        print(f'  {i}. {t["footballer"]}: +{t["amount"]:,}')
        if t['league_player_associated']:
            print(f'     To: {t["league_player_associated"]}')

    # Top trading partners
    print(f'\n🤝 TOP {print_top_n} TRADING PARTNERS (by Net Exchange):')
    for i, partner in enumerate(analytics['top_trading_partners'][:print_top_n], 1):
        print(f'  {i}. {partner["partner"]}')
        print(f'     Purchases: {partner["purchases"]} | Sales: {partner["sales"]}')
        print(f'     Spent: {partner["spent"]:,} | Earned: {partner["earned"]:,}')
        print(f'     Net Exchange: {partner["net_exchange"]:+,}')

    # Clause increase summary
    print('\n⚠️  CLAUSE INCREASE SUMMARY:')
    clause_sum = analytics['clause_increase_summary']
    print(f'  Total Increases: {clause_sum["total_count"]}')
    print(f'  Total Cost: {clause_sum["total_cost"]:,}')
    print(f'  Average Cost: {clause_sum["avg_cost"]:,.0f}')

    # Current squad
    print(f'\n👥 CURRENT SQUAD INVESTMENT: {analytics["current_squad_total_investment"]:,}')
    print(f'  Players in squad: {len(analytics["current_squad"])}')
    print('  Squad investments:')
    for i, player in enumerate(analytics['current_squad'][:print_top_n], 1):
        print(f'    {i}. {player["player"]}: {player["total_invested"]:,}')

    print('\n' + '=' * 70)


def main(input_html, output_pdf, print_top_n):
    transactions = _parse_html(input_html)
    analytics = _analyze(transactions)
    _print_analytics(analytics, print_top_n)


if __name__ == '__main__':
    args = parse_args()
    main(args.input_html, args.output_pdf, args.print_top_n)
