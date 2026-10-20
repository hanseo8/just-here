/* A payout hold is already debited from the server balance. Never deduct it twice. */
(function(root){
  function summarize(data){
    const payouts=data.payouts||[];
    const sum=statuses=>payouts.filter(p=>statuses.includes(p.status)).reduce((n,p)=>n+Number(p.amount_krw||0),0);
    return {available:Number(data.balance||0),pending:Number(data.pending_points||0),reserved:sum(['pending','processing']),paid:sum(['paid'])};
  }
  root.JustHereWallet={summarize};
})(typeof window!=='undefined'?window:globalThis);
