/* Keep one form file field: choosing camera or album never submits a receipt. */
(function(){
  const input=document.getElementById('receipt-image');
  const message=document.getElementById('image-status');
  function choose(camera){
    if(camera)input.setAttribute('capture','environment');
    else input.removeAttribute('capture');
    message.textContent=camera?'카메라를 여는 중이에요. 기기에 따라 파일 선택 화면이 열릴 수 있어요.':'앨범이나 파일에서 영수증 사진을 선택해 주세요.';
    input.click();
  }
  document.getElementById('receipt-camera').onclick=()=>choose(true);
  document.getElementById('receipt-album').onclick=()=>choose(false);
  input.addEventListener('cancel',()=>{message.textContent=input.files?.length?'기존에 선택한 사진을 유지했어요.':'사진 선택을 취소했어요. 촬영 또는 앨범 선택을 다시 눌러 주세요.';});
})();
