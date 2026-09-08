import tempfile
import unittest
from pathlib import Path
from finance import FinanceStore, TRANSFER, month_shift
from core import Store
from xlsx_itau import parse_xlsx
from test_xlsx import fixture
import test_core


class FinanceTests(test_core.ImportTests):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=FinanceStore(Path(self.temp.name)/'test.db')
        self.store.add_account('Itaú conta','Conta corrente')
        self.store.add_account('Itaú cartão','Cartão de crédito')

    def purchase(self, month='2026-10', part=2, ownership='Titular', value=-10000):
        return dict(date='2026-08-01',description=f'Loja · Parcela {part} de 4 · ****0001 · {ownership}',
            amount=value,fitid='',invoice_month=month,ownership=ownership,holder='Portador fictício',
            card_number='****0001',invoice_metadata=True,invoice_due=month+'-08',invoice_state='Aberta',invoice_total=20000)

    def save_rows(self, account, name, rows):
        return self.store.save(account,name,name.encode(),self.store.preview(account,rows))

    def test_invoice_combines_holders_and_forecasts_stay_separate(self):
        self.save_rows(2,'a',[self.purchase(),self.purchase(ownership='Adicional')])
        invoice=self.store.invoices()[0]
        self.assertEqual(invoice['calculated'],20000)
        self.assertEqual(invoice['due'],'2026-10-08')
        self.assertEqual(len(self.store.transactions(ownership='Adicional')),1)
        forecast=self.store.forecasts()
        self.assertEqual(len(forecast),4)
        self.assertEqual(sum(r['amount'] for r in forecast),40000)
        self.assertEqual(len(self.store.transactions()),2)
        self.save_rows(2,'b',[self.purchase('2026-11',3),self.purchase('2026-11',3,ownership='Adicional')])
        self.assertEqual(len(self.store.forecasts()),2)
        self.assertEqual({r['month'] for r in self.store.forecasts()},{'2026-12'})

    def test_payment_pair_invoice_and_undo(self):
        self.save_rows(2,'bill',[self.purchase()])
        d=dict(date='2026-10-08',description='FATURA PAGA',amount=-10000,fitid='d',category=TRANSFER)
        c=dict(date='2026-10-09',description='Pagamento Com Saldo',amount=10000,fitid='c',category=TRANSFER)
        self.save_rows(1,'debit',[d]);self.save_rows(2,'credit',[c])
        pairs=self.store.payment_candidates();self.assertEqual(len(pairs),1)
        debit,credit=pairs[0]
        self.store.reconcile(debit['id'],credit['id'],'2026-10')
        self.assertEqual(self.store.invoices()[0]['paid'],10000)
        self.assertEqual(self.store.invoices()[0]['remaining'],10000)
        self.assertEqual(self.store.payment_candidates(),[])
        with self.assertRaises(ValueError): self.store.reconcile(debit['id'],credit['id'])
        with self.assertRaises(ValueError): self.store.categorize([debit['id']],'Compras')
        self.store.undo()
        self.assertEqual(self.store.invoices()[0]['paid'],0)
        self.assertEqual(len(self.store.reconciled()),0)

    def test_budget_comparison_rules_and_edit_dedup(self):
        self.save_rows(1,'a',[dict(date='2026-09-08',description='Mercado',amount=-1000,fitid='1')])
        self.save_rows(1,'b',[dict(date='2026-10-08',description='Mercado',amount=-2000,fitid='2')])
        self.store.save_rule('','mercado','Mercado',True)
        self.store.set_budget('2026-10','Mercado',1500)
        self.assertEqual(self.store.budget_report('2026-10')[0]['remaining'],-500)
        self.assertEqual(self.store.comparison('2026-10')[0]['difference'],1000)
        row=self.store.transactions('2026-10')[0]
        self.store.edit_transaction(row['id'],1,'09/10/2026','Corrigido',-2500,'Mercado')
        original=dict(date='2026-10-08',description='Mercado',amount=-2000,fitid='2')
        self.assertEqual(self.store.preview(1,[original])[0]['status'],'Duplicado (ID)')
        self.store.edit_transaction(None,1,'10/10/2026','Manual',-100,'Compras')
        self.assertEqual(len(self.store.transactions()),3)
        self.store.delete_rule('mercado');self.assertEqual(self.store.category('Mercado'),'Sem categoria')
        self.store.delete_budget('2026-10','Mercado');self.assertEqual(self.store.budget_report('2026-10'),[])

    def test_snapshot_refresh_with_no_new_transactions(self):
        rows=[self.purchase()]
        self.save_rows(2,'a',rows)
        updated=dict(rows[0],invoice_state='Fechada',invoice_total=25000)
        self.assertEqual(self.save_rows(2,'b',[updated]),0)
        self.assertEqual(self.store.invoices()[0]['state'],'Fechada')
        self.store.undo()
        self.assertEqual(self.store.invoices()[0]['state'],'Aberta')
        self.store.set_invoice(2,'2026-10','09/10/2026','Fechada',22000)
        self.assertEqual(self.store.invoices()[0]['remaining'],22000)

    def test_migration_preserves_existing_data(self):
        path=Path(self.temp.name)/'old.db'
        old=Store(path);old.add_account('Cartão','Cartão de crédito')
        r=self.purchase();old.save(1,'a',b'a',old.preview(1,[r]));old.db.close()
        new=FinanceStore(path)
        self.assertEqual(len(new.transactions()),1)
        self.assertEqual(new.transactions()[0]['ownership'],'Titular')
        self.assertEqual(new.save(1,'a',b'a',new.preview(1,[r])),0)
        self.assertEqual(new.invoices()[0]['due'],'2026-10-08')
        self.assertEqual(new.transactions()[0]['holder'],'Portador fictício')
        new.db.close()

    def test_parser_metadata_and_month_rollover(self):
        r=parse_xlsx(fixture())[0]
        self.assertTrue(r['invoice_metadata'])
        self.assertEqual(r['invoice_state'],'Aberta')
        self.assertEqual(month_shift('2026-12',1),'2027-01')
        with self.assertRaises(ValueError): self.store.set_budget('2026-13','Mercado',100)

    def test_xlsx_header_and_additional_owner(self):
        import io,zipfile
        from xml.etree import ElementTree as ET
        namespace='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        def tag(name): return '{'+namespace+'}'+name
        raw=fixture()
        out=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as src,zipfile.ZipFile(out,'w') as dest:
            for name in src.namelist():
                content=src.read(name)
                if name=='xl/worksheets/sheet1.xml':
                    root=ET.fromstring(content)
                    data=root.find(tag('sheetData'))
                    def cell(row,ref,value):
                        c=ET.SubElement(row,tag('c'),r=ref,t='inlineStr')
                        ET.SubElement(ET.SubElement(c,tag('is')),tag('t')).text=value
                    header=ET.Element(tag('row'),r='80')
                    cell(header,'G80','Valor (parcial)');cell(header,'I80','Vencimento')
                    values=ET.Element(tag('row'),r='81')
                    cell(values,'G81','12.34');cell(values,'I81','2026-10-08')
                    data.insert(1,header);data.insert(2,values)
                    for row in data:
                        if row.get('r')=='2':
                            cell(row,'G2','Titularidade');cell(row,'H2','Nome');cell(row,'I2','Número do cartão')
                        if row.get('r')=='3':
                            cell(row,'G3','Adicional');cell(row,'H3','Pessoa fictícia');cell(row,'I3','****0002')
                    content=ET.tostring(root)
                dest.writestr(name,content)
        row=parse_xlsx(out.getvalue())[0]
        self.assertEqual(row['invoice_due'],'2026-10-08')
        self.assertEqual(row['invoice_total'],1234)
        self.assertEqual(row['ownership'],'Adicional')
        self.assertEqual(row['holder'],'Pessoa fictícia')
        self.assertEqual(row['card_number'],'****0002')
