import argparse
import re

from bs4 import BeautifulSoup


def parse_args():
    parser = argparse.ArgumentParser(description='Mister Balance Analyzer')
    parser.add_argument('--input_html', type=str, required=True, help='Input HTMLfile')
    parser.add_argument('--output_pdf', type=str, required=True, help='Output PDF file')
    args = parser.parse_args()
    return args


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
        transaction_type = type_div.get_text(strip=True) if type_div else ''
        # Extract reason/description
        reason_div = left_div.find('div', class_='reason')
        reason = reason_div.get_text(strip=True, separator=' ') if reason_div else ''
        # Extract date
        date_div = left_div.find('div', class_='date')
        date_full = date_div.get('title', '') if date_div else ''
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
        # Determine if it's positive or negative
        is_positive = 'green' in amount_div.get('class', []) if amount_div else False
        is_negative = 'red' in amount_div.get('class', []) if amount_div else False
        # Add transaction to list
        transactions.append(
            {
                'type': transaction_type,
                'reason': reason,
                'date_full': date_full,
                'amount': amount,
                'balance_after': balance_after,
                'is_positive': is_positive,
                'is_negative': is_negative,
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
