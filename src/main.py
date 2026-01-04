import argparse
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup


def parse_args():
    parser = argparse.ArgumentParser(description='Mister Balance Analyzer')
    parser.add_argument('--input_html', type=str, required=True, help='Input HTMLfile')
    parser.add_argument('--output_pdf', type=str, required=True, help='Output PDF file')
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
    print(f'Found {len(transactions)} transactions')
    return transactions


def main(input_html, output_pdf):
    transactions = _parse_html(input_html)


if __name__ == '__main__':
    args = parse_args()
    main(args.input_html, args.output_pdf)
