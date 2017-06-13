function getUrlBase() {

    var DEBUG = true

    if (DEBUG) {
        return "http://localhost:5000/"
    } else {
        return "http://localhost:5000/analiseserver/"
    }

}

function getCookie(cname) {
    var name = cname + "=";
    var decodedCookie = decodeURIComponent(document.cookie);
    var ca = decodedCookie.split(';');
    for(var i = 0; i <ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) == 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
}

function validarOauth(n) {
    var data = getCookie('analisetoken');
    if (data) {
        data = JSON.parse(data);
        $.ajax({
            url: getUrlBase()+"/login/validar?usuario="+data.usuario+"&token="+data.token,
            cache: false,
            success: function(){
                $('#lblLogin').text(data.usuario);
            },
            error: function(erro) {
                if (n){
                    window.location.href = "../../login.html";
                } else {
                    window.location.href = "login.html";
                }
            }
        });

    } else {
        if (n){
            window.location.href = "../../login.html";
        } else {
            window.location.href = "login.html";
        }
    }
}
