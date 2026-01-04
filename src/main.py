import argparse
import io
import re
from collections import defaultdict
from datetime import datetime, timezone

import matplotlib
import matplotlib.pyplot as plt
from bs4 import BeautifulSoup
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

matplotlib.use('Agg')  # Use non-interactive backend


def parse_args():
    parser = argparse.ArgumentParser(description='Mister Balance Analyzer')
    parser.add_argument('--input_html', type=str, required=True, help='Input HTML file')
    parser.add_argument('--output_pdf', type=str, required=True, help='Output PDF file')
    parser.add_argument('--date-range', type=str, help='Date range filter (format: YYYY-MM-DD,YYYY-MM-DD)')
    return parser.parse_args()


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


def __create_chart_transaction_types(analytics):
    # Create pie chart for transaction types
    fig, ax = plt.subplots(figsize=(6, 4))
    type_summary = analytics['type_summary']
    # Only show types with transactions
    types = []
    counts = []
    for trans_type, summary in sorted(type_summary.items()):
        if summary['count'] > 0:
            types.append(trans_type)
            counts.append(summary['count'])
    colors_list = plt.cm.Set3(range(len(types)))
    ax.pie(counts, labels=types, autopct='%1.1f%%', colors=colors_list, startangle=90)
    ax.set_title('Transaction Distribution')
    plt.tight_layout()
    # Save to bytes
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    plt.close()
    return img_buffer


def __create_chart_balance_timeline(transactions):
    # Create line chart for balance over time
    if not transactions:
        return None
    fig, ax = plt.subplots(figsize=(8, 4))
    # Sort by date
    sorted_trans = sorted([t for t in transactions if t['date_full']], key=lambda x: x['date_full'])
    if not sorted_trans:
        plt.close()
        return None
    dates = [t['date_full'] for t in sorted_trans]
    balances = [t['balance_after'] for t in sorted_trans]
    ax.plot(dates, balances, linewidth=2, color='#2e7d32', marker='o', markersize=2)
    ax.set_title('Balance Over Time')
    ax.set_xlabel('Date')
    ax.set_ylabel('Balance')
    ax.grid(True, alpha=0.3)

    # Format Y-axis in millions
    def millions_formatter(x, pos):
        return f'{x/1e6:.0f}M'

    ax.yaxis.set_major_formatter(plt.FuncFormatter(millions_formatter))
    plt.xticks(rotation=45)
    plt.tight_layout()
    # Save to bytes
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    plt.close()
    return img_buffer


def __create_chart_roi_distribution(analytics):
    # Create bar chart for top ROI players
    fig, ax = plt.subplots(figsize=(8, 5))
    best_roi = analytics['best_roi_players'][:10]
    if not best_roi:
        plt.close()
        return None
    players = [p['player'][:15] + '...' if len(p['player']) > 15 else p['player'] for p in best_roi]
    roi_values = [p['roi_percentage'] for p in best_roi]
    colors_list = ['#2e7d32' if v > 0 else '#c62828' for v in roi_values]
    ax.barh(players, roi_values, color=colors_list)
    ax.set_xlabel('ROI (%)')
    ax.set_title('Top 10 Players by ROI')
    ax.grid(True, axis='x', alpha=0.3)
    plt.tight_layout()
    # Save to bytes
    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format='png', dpi=150, bbox_inches='tight')
    img_buffer.seek(0)
    plt.close()
    return img_buffer


def _parse_html(input_html):
    # Read the HTML content
    with open(input_html, 'r', encoding='utf-8') as f:
        html_content = f.read()
    # Parse the HTML content
    soup = BeautifulSoup(html_content, 'html.parser')
    # Find the balance history section
    balance_history = soup.find('ul', class_='balance-history')
    if not balance_history:
        print('⚠️ No balance history found')
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
    print(f'✅ {len(transactions)} transactions parsed')
    return transactions


def _filter_transactions_by_date(transactions, date_range_str):
    if not date_range_str:
        return transactions
    try:
        start_str, end_str = date_range_str.split(',')
        start_date = datetime.strptime(start_str.strip(), '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(end_str.strip(), '%Y-%m-%d').replace(tzinfo=timezone.utc)
        filtered = [t for t in transactions if t['date_full'] and start_date <= t['date_full'] <= end_date]
        print(f'📅 Filtered to {len(filtered)} transactions between {start_str} and {end_str}')
        return filtered
    except Exception as e:
        print(f'⚠️ Error parsing date range: {e}. Using all transactions.')
        return transactions


def _analyze(transactions):
    analytics = {}

    # 1. Player profitability analysis
    print('Analyzing player profitability...')
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
    print('Analyzing total profitability...')
    total_profitability = sum(p['net_profit'] for p in player_profitability)
    analytics['total_profitability'] = total_profitability

    # 3. Ranking of buyouts (most expensive buyout signings and sales)
    print('Analyzing buyout signings...')
    buyout_signings = [t for t in transactions if t['type'] == 'buyout_signing']
    buyout_signings.sort(key=lambda x: abs(x['amount']), reverse=True)
    analytics['top_buyout_signings'] = buyout_signings
    buyout_sales = [t for t in transactions if t['type'] == 'buyout_sale']
    buyout_sales.sort(key=lambda x: x['amount'], reverse=True)
    analytics['top_buyout_sales'] = buyout_sales

    # 4. Transaction type breakdown
    print('Analyzing transaction type breakdown...')
    type_summary = defaultdict(lambda: {'count': 0, 'total_amount': 0, 'avg_amount': 0})
    for t in transactions:
        type_summary[t['type']]['count'] += 1
        type_summary[t['type']]['total_amount'] += t['amount']
    for trans_type in type_summary:
        count = type_summary[trans_type]['count']
        type_summary[trans_type]['avg_amount'] = type_summary[trans_type]['total_amount'] / count if count > 0 else 0
    analytics['type_summary'] = dict(type_summary)

    # 5. Most active trading partners (league players)
    print('Analyzing most active trading partners...')
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
    print('Analyzing biggest losses...')
    biggest_losses = [p for p in player_profitability if p['net_profit'] < 0]
    biggest_losses.sort(key=lambda x: x['net_profit'])
    analytics['biggest_losses'] = biggest_losses

    # 7. Best deals (highest profit players)
    print('Analyzing best deals...')
    best_deals = [p for p in player_profitability if p['net_profit'] > 0]
    best_deals.sort(key=lambda x: x['net_profit'], reverse=True)
    analytics['best_deals'] = best_deals

    # 8. Clause increase analysis
    print('Analyzing clause increase analysis...')
    clause_increases = [t for t in transactions if t['type'] == 'clause_increase']
    total_clause_cost = sum(abs(t['amount']) for t in clause_increases)
    analytics['clause_increase_summary'] = {
        'total_count': len(clause_increases),
        'total_cost': total_clause_cost,
        'avg_cost': total_clause_cost / len(clause_increases) if clause_increases else 0,
    }

    # 9. Current squad value (players purchased but not sold, or initial squad with clause increases)
    print('Analyzing current squad value...')
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

    # 10. Average Hold Time & ROI
    print('Analyzing hold time and ROI...')
    hold_times = []
    roi_data = []
    for player, data in player_transactions.items():
        if data['sales'] and data['purchases']:
            # Calculate hold time (from first purchase to last sale)
            first_purchase_date = min(t['date_full'] for t in data['purchases'] if t['date_full'])
            last_sale_date = max(t['date_full'] for t in data['sales'] if t['date_full'])
            if first_purchase_date and last_sale_date:
                hold_days = (last_sale_date - first_purchase_date).days
                hold_times.append(hold_days)
                # Calculate ROI
                total_spent = sum(abs(t['amount']) for t in data['purchases'])
                total_spent += sum(abs(t['amount']) for t in data['clause_increases'])
                total_earned = sum(t['amount'] for t in data['sales'])
                net_profit = total_earned - total_spent
                roi_percentage = (net_profit / total_spent * 100) if total_spent > 0 else 0
                roi_data.append(
                    {
                        'player': player,
                        'roi_percentage': roi_percentage,
                        'net_profit': net_profit,
                        'total_spent': total_spent,
                        'total_earned': total_earned,
                        'hold_days': hold_days,
                    }
                )
    analytics['average_hold_time'] = sum(hold_times) / len(hold_times) if hold_times else 0
    analytics['roi_data'] = sorted(roi_data, key=lambda x: x['roi_percentage'], reverse=True)
    analytics['best_roi_players'] = [p for p in analytics['roi_data'] if p['roi_percentage'] > 0][:20]
    analytics['worst_roi_players'] = [p for p in analytics['roi_data'] if p['roi_percentage'] < 0][-20:]

    # 11. Win Rate
    print('Analyzing win rate...')
    profitable_trades = len([p for p in roi_data if p['net_profit'] > 0])
    total_trades = len(roi_data)
    analytics['win_rate'] = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
    analytics['total_trades'] = total_trades
    analytics['profitable_trades'] = profitable_trades
    analytics['losing_trades'] = total_trades - profitable_trades

    return analytics


def _save_pdf(analytics, output_pdf, transactions):
    # Create PDF document
    doc = SimpleDocTemplate(output_pdf, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18)
    story = []
    styles = getSampleStyleSheet()
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=30,
        alignment=1,
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#0f3460'),
        spaceAfter=12,
        spaceBefore=12,
    )
    subheading_style = ParagraphStyle(
        'CustomSubHeading', parent=styles['Heading3'], fontSize=12, textColor=colors.HexColor('#16213e'), spaceAfter=8
    )
    # Title
    story.append(Paragraph('MISTER BALANCE ANALYTICS', title_style))
    story.append(Spacer(1, 0.2 * inch))
    # Executive Summary
    story.append(Paragraph('Executive Summary', heading_style))
    # Create summary dashboard with key metrics
    summary_data = [
        ['Metric', 'Value'],
        ['Total Profitability', f'{analytics["total_profitability"]:,}'],
        ['Win Rate', f'{analytics["win_rate"]:.1f}%'],
        ['Total Trades', f'{analytics["total_trades"]}'],
        ['Profitable Trades', f'✓ {analytics["profitable_trades"]}'],
        ['Losing Trades', f'✗ {analytics["losing_trades"]}'],
        ['Avg Hold Time', f'{analytics["average_hold_time"]:.0f} days'],
        ['Current Squad Investment', f'{analytics["current_squad_total_investment"]:,}'],
        ['Players in Squad', f'{len(analytics["current_squad"])}'],
    ]
    summary_table = Table(summary_data, colWidths=[3 * inch, 3 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#e8eaf6')),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#e8eaf6'), colors.HexColor('#f5f5f5')]),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 0.3 * inch))
    # Add Charts
    story.append(Paragraph('Performance Charts', heading_style))
    # Balance Timeline Chart
    balance_chart = __create_chart_balance_timeline(transactions)
    if balance_chart:
        story.append(Image(balance_chart, width=6 * inch, height=3 * inch))
        story.append(Spacer(1, 0.2 * inch))
    # Transaction Type Pie Chart
    type_chart = __create_chart_transaction_types(analytics)
    if type_chart:
        story.append(Image(type_chart, width=5 * inch, height=3 * inch))
        story.append(Spacer(1, 0.2 * inch))
    # ROI Distribution Chart
    roi_chart = __create_chart_roi_distribution(analytics)
    if roi_chart:
        story.append(Image(roi_chart, width=6 * inch, height=4 * inch))
    story.append(PageBreak())
    # Total Profitability
    story.append(Paragraph('Total Profitability (Sold Players)', heading_style))
    profit_data = [[f'{analytics["total_profitability"]:,}']]
    profit_table = Table(profit_data, colWidths=[5 * inch])
    profit_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e8f5e9')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#2e7d32')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 18),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 12),
            ]
        )
    )
    story.append(profit_table)
    story.append(Spacer(1, 0.3 * inch))
    # Transaction Type Breakdown
    story.append(Paragraph('Transaction Type Breakdown', heading_style))
    type_data = [['Type', 'Count', 'Total', 'Average']]
    for trans_type, summary in sorted(analytics['type_summary'].items()):
        type_data.append(
            [trans_type, str(summary['count']), f'{summary["total_amount"]:,}', f'{summary["avg_amount"]:,.0f}']
        )
    type_table = Table(type_data, colWidths=[2 * inch, 1 * inch, 1.5 * inch, 1.5 * inch])
    type_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a237e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]
        )
    )
    story.append(type_table)
    story.append(Spacer(1, 0.3 * inch))
    # Best Deals
    story.append(Paragraph('Best Deals (Highest Profit)', heading_style))
    best_data = [['#', 'Player', 'Spent', 'Earned', 'Net Profit']]
    for i, player in enumerate(analytics['best_deals'], 1):
        best_data.append(
            [
                str(i),
                player['player'],
                f'{player["total_spent"]:,}',
                f'{player["total_earned"]:,}',
                f'+{player["net_profit"]:,}',
            ]
        )
    best_table = Table(best_data, colWidths=[0.3 * inch, 2 * inch, 1.2 * inch, 1.2 * inch, 1.3 * inch])
    best_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2e7d32')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f1f8e9')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(best_table)
    story.append(PageBreak())
    # Biggest Losses
    story.append(Paragraph('Biggest Losses', heading_style))
    loss_data = [['#', 'Player', 'Spent', 'Earned', 'Net Loss']]
    for i, player in enumerate(analytics['biggest_losses'], 1):
        loss_data.append(
            [
                str(i),
                player['player'],
                f'{player["total_spent"]:,}',
                f'{player["total_earned"]:,}',
                f'{player["net_profit"]:,}',
            ]
        )
    loss_table = Table(loss_data, colWidths=[0.3 * inch, 2 * inch, 1.2 * inch, 1.2 * inch, 1.3 * inch])
    loss_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c62828')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ffebee')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(loss_table)
    story.append(Spacer(1, 0.3 * inch))
    # Top Buyout Signings
    story.append(Paragraph('Most Expensive Buyout Signings', heading_style))
    signing_data = [['#', 'Player', 'Amount', 'From']]
    for i, t in enumerate(analytics['top_buyout_signings'], 1):
        signing_data.append(
            [str(i), t['footballer'], f'{t["amount"]:,}', t.get('league_player_associated', '-') or '-']
        )
    signing_table = Table(signing_data, colWidths=[0.3 * inch, 2 * inch, 1.5 * inch, 2.2 * inch])
    signing_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d84315')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fbe9e7')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(signing_table)
    story.append(PageBreak())
    # Top Buyout Sales
    story.append(Paragraph('Highest Buyout Sales', heading_style))
    sale_data = [['#', 'Player', 'Amount', 'To']]
    for i, t in enumerate(analytics['top_buyout_sales'], 1):
        sale_data.append([str(i), t['footballer'], f'+{t["amount"]:,}', t.get('league_player_associated', '-') or '-'])
    sale_table = Table(sale_data, colWidths=[0.3 * inch, 2 * inch, 1.5 * inch, 2.2 * inch])
    sale_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#388e3c')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#e8f5e9')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(sale_table)
    story.append(Spacer(1, 0.3 * inch))
    # Trading Partners
    story.append(Paragraph('Trading Partners (by Net Exchange)', heading_style))
    partner_data = [['#', 'Partner', 'Purchases', 'Sales', 'Net Exchange']]
    for i, partner in enumerate(analytics['top_trading_partners'], 1):
        net_sign = '+' if partner['net_exchange'] >= 0 else ''
        partner_data.append(
            [
                str(i),
                partner['partner'],
                str(partner['purchases']),
                str(partner['sales']),
                f'{net_sign}{partner["net_exchange"]:,}',
            ]
        )
    partner_table = Table(partner_data, colWidths=[0.3 * inch, 2.2 * inch, 1 * inch, 1 * inch, 1.5 * inch])
    partner_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1565c0')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#e3f2fd')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(partner_table)
    story.append(PageBreak())
    # Clause Increase Summary
    story.append(Paragraph('Clause Increase Summary', heading_style))
    clause_sum = analytics['clause_increase_summary']
    clause_data = [
        ['Total Increases', 'Total Cost', 'Average Cost'],
        [str(clause_sum['total_count']), f'{clause_sum["total_cost"]:,}', f'{clause_sum["avg_cost"]:,.0f}'],
    ]
    clause_table = Table(clause_data, colWidths=[2 * inch, 2 * inch, 2 * inch])
    clause_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f57c00')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fff3e0')),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ]
        )
    )
    story.append(clause_table)
    story.append(Spacer(1, 0.3 * inch))
    # Current Squad
    story.append(Paragraph(f'Current Squad Investment: {analytics["current_squad_total_investment"]:,}', heading_style))
    story.append(Paragraph(f'Players in squad: {len(analytics["current_squad"])}', subheading_style))
    squad_data = [['#', 'Player', 'Total Invested']]
    for i, player in enumerate(analytics['current_squad'], 1):
        squad_data.append([str(i), player['player'], f'{player["total_invested"]:,}'])
    squad_table = Table(squad_data, colWidths=[0.5 * inch, 3.5 * inch, 2 * inch])
    squad_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6a1b9a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f3e5f5')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(squad_table)
    story.append(PageBreak())
    # ROI Analysis
    story.append(Paragraph('ROI Analysis (Return on Investment)', heading_style))
    story.append(Paragraph(f'Average Hold Time: {analytics["average_hold_time"]:.0f} days', subheading_style))
    # Best ROI Players
    story.append(Paragraph('Best ROI Players', subheading_style))
    roi_best_data = [['#', 'Player', 'ROI %', 'Profit', 'Hold Days']]
    for i, player in enumerate(analytics['best_roi_players'][:20], 1):
        roi_best_data.append(
            [
                str(i),
                player['player'],
                f'{player["roi_percentage"]:.1f}%',
                f'+{player["net_profit"]:,}',
                str(player['hold_days']),
            ]
        )
    roi_best_table = Table(roi_best_data, colWidths=[0.3 * inch, 2.5 * inch, 1 * inch, 1.5 * inch, 0.7 * inch])
    roi_best_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2e7d32')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f1f8e9')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(roi_best_table)
    story.append(Spacer(1, 0.3 * inch))
    # Worst ROI Players
    story.append(Paragraph('Worst ROI Players', subheading_style))
    roi_worst_data = [['#', 'Player', 'ROI %', 'Loss', 'Hold Days']]
    for i, player in enumerate(analytics['worst_roi_players'][:20], 1):
        roi_worst_data.append(
            [
                str(i),
                player['player'],
                f'{player["roi_percentage"]:.1f}%',
                f'{player["net_profit"]:,}',
                str(player['hold_days']),
            ]
        )
    roi_worst_table = Table(roi_worst_data, colWidths=[0.3 * inch, 2.5 * inch, 1 * inch, 1.5 * inch, 0.7 * inch])
    roi_worst_table.setStyle(
        TableStyle(
            [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c62828')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ffebee')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(roi_worst_table)
    # Build PDF
    doc.build(story)
    print(f'✅ PDF saved to: {output_pdf}')


def main(input_html, output_pdf, date_range=None):
    transactions = _parse_html(input_html)
    if transactions:
        if date_range:
            transactions = _filter_transactions_by_date(transactions, date_range)
        analytics = _analyze(transactions)
        _save_pdf(analytics, output_pdf, transactions)


if __name__ == '__main__':
    args = parse_args()
    main(args.input_html, args.output_pdf, args.date_range)
