
$( '#partner_email' ).select2( {
  theme: 'bootstrap-5'
} );

$( '#id_org_partner' ).select2( {
	theme: 'bootstrap-5'
  } );

$( '#author' ).select2( {
  theme: 'bootstrap-5'
} );
$( '#id_author' ).select2( {
	theme: 'bootstrap-5'
  } );

function slugify(text) {
	return text
	  .toString() // Cast to string
	  .toLowerCase() // Convert the string to lowercase letters
	  .normalize('NFD') // The normalize() method returns the Unicode Normalization Form of a given string.
	  .trim() // Remove whitespace from both sides of a string
	  .replace(/\s+/g, '-') // Replace spaces with -
	  .replace(/[^\w\-]+/g, '') // Remove all non-word chars
	  .replace(/\-\-+/g, '-'); // Replace multiple - with single -
  }
  
  function listingslug(text) {
	document.getElementById("id_slug").value = slugify(text);
  }


var emails = "ab@gmail.comefgh@gmail.comterb@gmail.com"
var emailsArray = new Array()

while (emails !== '')
{
  //ensures that dot is searched after @ symbol (so it can find this email as well: test.test@test.com)
  //adding 4 characters makes up for dot + TLD ('.com'.length === 4)
  var endOfEmail = emails.indexOf('.',emails.indexOf('@')) + 4
  var tmpEmail = emails.substring(0, endOfEmail)
  emails = emails.substring(endOfEmail)
  emailsArray.push(tmpEmail)
}

console.log(emailsArray)
 




          
  