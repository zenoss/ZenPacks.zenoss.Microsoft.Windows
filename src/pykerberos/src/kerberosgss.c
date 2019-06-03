/**
 * Copyright (c) 2006-2013 Apple Inc. All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 **/

#include <Python.h>
#include "kerberosgss.h"

#include "base64.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <endian.h>
#include <arpa/inet.h>

#if __BYTE_ORDER == __BIG_ENDIAN
#define Swap4Bytes(val) val
#else
#define Swap4Bytes(val) \
( (((val) >> 24) & 0x000000FF) | (((val) >>  8) & 0x0000FF00) | \
   (((val) <<  8) & 0x00FF0000) | (((val) << 24) & 0xFF000000) )
#endif

static void set_gss_error(OM_uint32 err_maj, OM_uint32 err_min);

extern PyObject *GssException_class;
extern PyObject *KrbException_class;

char* server_principal_details(const char* service, const char* hostname)
{
    char match[1024];
    size_t match_len = 0;
    char* result = NULL;
    
    int code;
    krb5_context kcontext;
    krb5_keytab kt = NULL;
    krb5_kt_cursor cursor = NULL;
    krb5_keytab_entry entry;
    char* pname = NULL;
    
    // Generate the principal prefix we want to match
    snprintf(match, 1024, "%s/%s@", service, hostname);
    match_len = strlen(match);
    
    code = krb5_init_context(&kcontext);
    if (code)
    {
        PyErr_SetObject(KrbException_class, Py_BuildValue("((s:i))",
                                                          "Cannot initialize Kerberos5 context", code));
        return NULL;
    }
    
    if ((code = krb5_kt_default(kcontext, &kt)))
    {
        PyErr_SetObject(KrbException_class, Py_BuildValue("((s:i))",
                                                          "Cannot get default keytab", code));
        goto end;
    }
    
    if ((code = krb5_kt_start_seq_get(kcontext, kt, &cursor)))
    {
        PyErr_SetObject(KrbException_class, Py_BuildValue("((s:i))",
                                                          "Cannot get sequence cursor from keytab", code));
        goto end;
    }
    
    while ((code = krb5_kt_next_entry(kcontext, kt, &entry, &cursor)) == 0)
    {
        if ((code = krb5_unparse_name(kcontext, entry.principal, &pname)))
        {
            PyErr_SetObject(KrbException_class, Py_BuildValue("((s:i))",
                                                              "Cannot parse principal name from keytab", code));
            goto end;
        }
        
        if (strncmp(pname, match, match_len) == 0)
        {
            result = malloc(strlen(pname) + 1);
            strcpy(result, pname);
            krb5_free_unparsed_name(kcontext, pname);
            krb5_free_keytab_entry_contents(kcontext, &entry);
            break;
        }
        
        krb5_free_unparsed_name(kcontext, pname);
        krb5_free_keytab_entry_contents(kcontext, &entry);
    }
    
    if (result == NULL)
    {
        PyErr_SetObject(KrbException_class, Py_BuildValue("((s:i))",
                                                          "Principal not found in keytab", -1));
    }
    
end:
    if (cursor)
        krb5_kt_end_seq_get(kcontext, kt, &cursor);
    if (kt)
        krb5_kt_close(kcontext, kt);
    krb5_free_context(kcontext);
    
    return result;
}

int authenticate_gss_client_init(const char* service, const char* principal, long int gss_flags, gss_client_state* state)
{
    OM_uint32 maj_stat;
    OM_uint32 min_stat;
    gss_buffer_desc name_token = GSS_C_EMPTY_BUFFER;
    gss_buffer_desc principal_token = GSS_C_EMPTY_BUFFER;
    int ret = AUTH_GSS_COMPLETE;
    gss_OID mech;

    state->server_name = GSS_C_NO_NAME;
    state->context = GSS_C_NO_CONTEXT;
    state->gss_flags = gss_flags;
    state->client_creds = GSS_C_NO_CREDENTIAL;
    state->username = NULL;
    state->response = NULL;
    
    // Import server name first
    name_token.length = strlen(service);
    name_token.value = (char *)service;


    // could be in principal name format, i.e. service/fqdn@REALM
    if (strchr(service, '/'))
        mech = GSS_C_NO_OID;
    else
        mech = gss_krb5_nt_service_name;

    maj_stat = gss_import_name(&min_stat, &name_token, mech, &state->server_name);
    
    if (GSS_ERROR(maj_stat))
    {
        set_gss_error(maj_stat, min_stat);
        ret = AUTH_GSS_ERROR;
        goto end;
    }
    
    // Get credential for principal
    if (principal && *principal)
    {
        gss_name_t name;
        principal_token.length = strlen(principal);
        principal_token.value = (char *)principal;

        maj_stat = gss_import_name(&min_stat, &principal_token, GSS_C_NT_USER_NAME, &name);
        if (GSS_ERROR(maj_stat))
        {
            set_gss_error(maj_stat, min_stat);
            ret = AUTH_GSS_ERROR;
	    goto end;
        }

        maj_stat = gss_acquire_cred(&min_stat, name, GSS_C_INDEFINITE, GSS_C_NO_OID_SET, GSS_C_INITIATE, 
                                    &state->client_creds, NULL, NULL);
        if (GSS_ERROR(maj_stat))
        {
            set_gss_error(maj_stat, min_stat);
            ret = AUTH_GSS_ERROR;
	    goto end;
        }

        maj_stat = gss_release_name(&min_stat, &name);
        if (GSS_ERROR(maj_stat))
        {
	    set_gss_error(maj_stat, min_stat);
            ret = AUTH_GSS_ERROR;
            goto end;
        }

      }

end:
    return ret;
}

int authenticate_gss_client_clean(gss_client_state *state)
{
    OM_uint32 maj_stat;
    OM_uint32 min_stat;
    int ret = AUTH_GSS_COMPLETE;
    
    if (state->context != GSS_C_NO_CONTEXT)
        maj_stat = gss_delete_sec_context(&min_stat, &state->context, GSS_C_NO_BUFFER);
    if (state->server_name != GSS_C_NO_NAME)
        maj_stat = gss_release_name(&min_stat, &state->server_name);
    if (state->client_creds != GSS_C_NO_CREDENTIAL)
        maj_stat = gss_release_cred(&min_stat, &state->client_creds);
    if (state->username != NULL)
    {
        free(state->username);
        state->username = NULL;
    }
    if (state->response != NULL)
    {
        free(state->response);
        state->response = NULL;
    }
    
    return ret;
}

int gss_get_client_context_time(gss_client_state *state, OM_uint32 *lifetime_rec)
{
    OM_uint32 maj_stat;
    OM_uint32 min_stat;
    int ret = AUTH_GSS_COMPLETE;

    if (state->context != GSS_C_NO_CONTEXT)
    {
        maj_stat = gss_context_time(&min_stat, state->context, lifetime_rec);

        if (maj_stat != GSS_S_COMPLETE)
        {
            set_gss_error(maj_stat, min_stat);
            if (maj_stat == GSS_S_CONTEXT_EXPIRED)
                ret = AUTH_GSS_EXPIRED;
            else
                ret = AUTH_GSS_ERROR;
        }
    }
    else
    {
        ret = AUTH_GSS_ERROR;
    }
    return ret;
}

int authenticate_gss_client_step(gss_client_state* state, const char* challenge)
{
    OM_uint32 maj_stat;
    OM_uint32 min_stat;
    OM_uint32 ret_flags; // Not used, but may be necessary for gss call.
    gss_buffer_desc input_token = GSS_C_EMPTY_BUFFER;
    gss_buffer_desc output_token = GSS_C_EMPTY_BUFFER;
    int ret = AUTH_GSS_CONTINUE;
    
    // Always clear out the old response
    if (state->response != NULL)
    {
        free(state->response);
        state->response = NULL;
    }
    
    // If there is a challenge (data from the server) we need to give it to GSS
    if (challenge && *challenge)
    {
        size_t len;
        input_token.value = base64_decode(challenge, &len);
        input_token.length = len;
    }
    
    // Do GSSAPI step
    Py_BEGIN_ALLOW_THREADS
    maj_stat = gss_init_sec_context(&min_stat,
                                    state->client_creds,
                                    &state->context,
                                    state->server_name,
                                    GSS_C_NO_OID,
                                    (OM_uint32)state->gss_flags,
                                    0,
                                    GSS_C_NO_CHANNEL_BINDINGS,
                                    &input_token,
                                    NULL,
                                    &output_token,
                                    &ret_flags,
                                    NULL);
    Py_END_ALLOW_THREADS
    
    if ((maj_stat != GSS_S_COMPLETE) && (maj_stat != GSS_S_CONTINUE_NEEDED))
    {
        set_gss_error(maj_stat, min_stat);
        ret = AUTH_GSS_ERROR;
        goto end;
    }
    
    ret = (maj_stat == GSS_S_COMPLETE) ? AUTH_GSS_COMPLETE : AUTH_GSS_CONTINUE;
    // Grab the client response to send back to the server
    if (output_token.length)
    {
        state->response = base64_encode((const unsigned char *)output_token.value, output_token.length);;
        maj_stat = gss_release_buffer(&min_stat, &output_token);
    }
    
    // Try to get the user name if we have completed all GSS operations
    if (ret == AUTH_GSS_COMPLETE)
    {
        gss_name_t gssuser = GSS_C_NO_NAME;
        maj_stat = gss_inquire_context(&min_stat, state->context, &gssuser, NULL, NULL, NULL,  NULL, NULL, NULL);
        if (GSS_ERROR(maj_stat))
        {
            set_gss_error(maj_stat, min_stat);
            ret = AUTH_GSS_ERROR;
            goto end;
        }
        
        gss_buffer_desc name_token;
        name_token.length = 0;
        maj_stat = gss_display_name(&min_stat, gssuser, &name_token, NULL);
        if (GSS_ERROR(maj_stat))
        {
            if (name_token.value)
                gss_release_buffer(&min_stat, &name_token);
            gss_release_name(&min_stat, &gssuser);
            
            set_gss_error(maj_stat, min_stat);
            ret = AUTH_GSS_ERROR;
            goto end;
        }
        else
        {
            state->username = (char *)malloc(name_token.length + 1);
            strncpy(state->username, (char*) name_token.value, name_token.length);
            state->username[name_token.length] = 0;
            gss_release_buffer(&min_stat, &name_token);
            gss_release_name(&min_stat, &gssuser);
        }
    }
end:
    if (output_token.value)
        gss_release_buffer(&min_stat, &output_token);
    if (input_token.value)
        free(input_token.value);
    return ret;
}

int authenticate_gss_client_unwrap(gss_client_state *state, const char *challenge)
{
	OM_uint32 maj_stat;
	OM_uint32 min_stat;
	gss_buffer_desc input_token = GSS_C_EMPTY_BUFFER;
	gss_buffer_desc output_token = GSS_C_EMPTY_BUFFER;
	int ret = AUTH_GSS_CONTINUE;
    int conf = 0;
    
	// Always clear out the old response
	if (state->response != NULL)
	{
		free(state->response);
		state->response = NULL;
        state->responseConf = 0;
	}
    
	// If there is a challenge (data from the server) we need to give it to GSS
	if (challenge && *challenge)
	{
		size_t len;
		input_token.value = base64_decode(challenge, &len);
		input_token.length = len;
	}
    
	// Do GSSAPI step
	maj_stat = gss_unwrap(&min_stat,
                          state->context,
                          &input_token,
                          &output_token,
                          &conf,
                          NULL);
    
	if (maj_stat != GSS_S_COMPLETE)
	{
		set_gss_error(maj_stat, min_stat);
		ret = AUTH_GSS_ERROR;
		goto end;
	}
	else
		ret = AUTH_GSS_COMPLETE;
    
	// Grab the client response
	if (output_token.length)
	{
		state->response = base64_encode((const unsigned char *)output_token.value, output_token.length);
        state->responseConf = conf;
		maj_stat = gss_release_buffer(&min_stat, &output_token);
	}
end:
	if (output_token.value)
		gss_release_buffer(&min_stat, &output_token);
	if (input_token.value)
		free(input_token.value);
	return ret;
}

#ifdef GSSAPI_EXT
int authenticate_gss_client_unwrap_iov(gss_client_state *state, const char *challenge)
{
        OM_uint32 maj_stat;
        OM_uint32 min_stat;
        int conf_state = 1;
        OM_uint32 qop_state = 0;
        int ret = AUTH_GSS_COMPLETE;
        int iov_count = 3;
        gss_iov_buffer_desc iov[iov_count];
        unsigned char * data = NULL;
        size_t len = 0;
        unsigned int token_len = 0;

        // Always clear out the old response
        if (state->response != NULL)
        {
            free(state->response);
            state->response = NULL;
            state->responseConf = 0;
        }

        // If there is a challenge (data from the server) we need to give it to GSS
        if (challenge && *challenge)
        {
            data = base64_decode(challenge, &len);
        }

        if (!data || len == 0)
        {
            // nothing to do, return
            data = (unsigned char *)malloc(1);
            data[0] = 0;
            state->response = (char*)data;
            return AUTH_GSS_COMPLETE;
        }

        memcpy(&token_len, data, sizeof(unsigned int));

        if (len-4-token_len < 0)
        {
            PyErr_SetObject(KrbException_class, Py_BuildValue("((s:i))","Data length error in response", -1));
            free(data);
            return AUTH_GSS_ERROR;
        }

        iov[0].type = GSS_IOV_BUFFER_TYPE_HEADER;
        iov[0].buffer.value = data+4;
        iov[0].buffer.length = token_len;

        iov[1].type = GSS_IOV_BUFFER_TYPE_DATA;
        iov[1].buffer.value = data+4+token_len;
		iov[1].buffer.length = len-4-token_len;

        iov[2].type = GSS_IOV_BUFFER_TYPE_DATA;
        iov[2].buffer.value = "";
        iov[2].buffer.length = 0;

        maj_stat = gss_unwrap_iov(&min_stat, state->context, &conf_state, &qop_state, iov, iov_count);
        
        if (maj_stat != GSS_S_COMPLETE)
        {
            set_gss_error(maj_stat, min_stat);
            ret = AUTH_GSS_ERROR;
        }
        else
        {
            ret = AUTH_GSS_COMPLETE;

            // Grab the client response
            state->responseConf = conf_state;
            state->response = base64_encode((const unsigned char *)iov[1].buffer.value, iov[1].buffer.length);
        }

        free(data);
        return ret;
}

int authenticate_gss_client_wrap_iov(gss_client_state* state, const char* challenge, int protect, int *pad_len)
{
    OM_uint32 maj_stat, min_stat;
    int iov_count = 3;
    gss_iov_buffer_desc iov[iov_count];
    size_t len = 0;
    int ret = AUTH_GSS_CONTINUE;
    int conf_state;
    unsigned char * data = (unsigned char*)"";

    // Always clear out the old response
    if (state->response != NULL)
    {
        free(state->response);
        state->response = NULL;
    }

    if (challenge && *challenge)
    {
        data = base64_decode(challenge, &len);
    }

    iov[0].type = GSS_IOV_BUFFER_TYPE_HEADER | GSS_IOV_BUFFER_FLAG_ALLOCATE;
    iov[1].type = GSS_IOV_BUFFER_TYPE_DATA;
    iov[1].buffer.value = data;
    iov[1].buffer.length = len;
    iov[2].type = GSS_IOV_BUFFER_TYPE_PADDING | GSS_IOV_BUFFER_FLAG_ALLOCATE;

    maj_stat = gss_wrap_iov(&min_stat,        /* minor_status */
                         state->context,         /* context_handle */
                         protect,       /* conf_req_flag */
                         GSS_C_QOP_DEFAULT, /* qop_req */
                         &conf_state,          /* conf_state */
                         iov,           /* iov */
                         iov_count);    /* iov_count */
    if (maj_stat != GSS_S_COMPLETE)
    {
        set_gss_error(maj_stat, min_stat);
        ret = AUTH_GSS_ERROR;
    }
    else
    {
        ret = AUTH_GSS_COMPLETE;

        int index = 4;
        OM_uint32 stoken_len= 0;
        int bufsize = iov[0].buffer.length+
                      iov[1].buffer.length+
                      iov[2].buffer.length+
                      sizeof(unsigned int);
        char * response = (char*)malloc(bufsize);
        memset(response,0,bufsize);
        /******************************************************
        Per Microsoft 2.2.9.1.2.2.2 for kerberos encrypted data
        First section of data is a 32-bit unsigned int containing
        the length of the Security Token followed by the encrypted message.
        Encrypted data = |32-bit unsigned int|Message|
        The message must start with the security token, followed by
        the actual encrypted message.
        Message = |Security Token|encrypted data|padding
        iov[0] = security token
        iov[1] = encrypted message
        iov[2] = padding
        ******************************************************/
        /* Security Token length */
        stoken_len = iov[0].buffer.length;
        memcpy(response, &stoken_len, sizeof(unsigned int));
        /* Security Token */
        memcpy(response+index, iov[0].buffer.value, iov[0].buffer.length);
        index += iov[0].buffer.length;
        /* Message */
        memcpy(response+index, iov[1].buffer.value, iov[1].buffer.length);
        index += iov[1].buffer.length;
        /* Padding */
        *pad_len = iov[2].buffer.length;
        if (*pad_len > 0)
        {
            memcpy(response+index, iov[2].buffer.value, iov[2].buffer.length);
            index += iov[2].buffer.length;
        }
        /* encode to python returnable string */
        state->responseConf = conf_state;
        state->response = base64_encode((const unsigned char *)response,index);
        free(response);
    }
    (void)gss_release_iov_buffer(&min_stat, iov, iov_count);
    free(data);
    return ret;
}
#endif

int authenticate_gss_client_wrap(gss_client_state* state, const char* challenge, const char* user, int protect)
{
	OM_uint32 maj_stat;
	OM_uint32 min_stat;
	gss_buffer_desc input_token = GSS_C_EMPTY_BUFFER;
	gss_buffer_desc output_token = GSS_C_EMPTY_BUFFER;
	int ret = AUTH_GSS_CONTINUE;
	char buf[4096], server_conf_flags;
	unsigned long buf_size;
    
	// Always clear out the old response
	if (state->response != NULL)
	{
		free(state->response);
		state->response = NULL;
	}
    
	if (challenge && *challenge)
	{
		size_t len;
		input_token.value = base64_decode(challenge, &len);
		input_token.length = len;
	}
    
	if (user) {
		// get bufsize
		server_conf_flags = ((char*) input_token.value)[0];
		((char*) input_token.value)[0] = 0;
		buf_size = ntohl(*((long *) input_token.value));
		free(input_token.value);
#ifdef PRINTFS
		printf("User: %s, %c%c%c\n", user,
               server_conf_flags & GSS_AUTH_P_NONE      ? 'N' : '-',
               server_conf_flags & GSS_AUTH_P_INTEGRITY ? 'I' : '-',
               server_conf_flags & GSS_AUTH_P_PRIVACY   ? 'P' : '-');
		printf("Maximum GSS token size is %ld\n", buf_size);
#endif
        
		// agree to terms (hack!)
		buf_size = htonl(buf_size); // not relevant without integrity/privacy
		memcpy(buf, &buf_size, 4);
		buf[0] = GSS_AUTH_P_NONE;
		// server decides if principal can log in as user
		strncpy(buf + 4, user, sizeof(buf) - 4);
		input_token.value = buf;
		input_token.length = 4 + strlen(user);
	}
    
	// Do GSSAPI wrap
	maj_stat = gss_wrap(&min_stat,
						state->context,
						protect,
						GSS_C_QOP_DEFAULT,
						&input_token,
						NULL,
						&output_token);
    
	if (maj_stat != GSS_S_COMPLETE)
	{
		set_gss_error(maj_stat, min_stat);
		ret = AUTH_GSS_ERROR;
		goto end;
	}
	else
		ret = AUTH_GSS_COMPLETE;
	// Grab the client response to send back to the server
	if (output_token.length)
	{
		state->response = base64_encode((const unsigned char *)output_token.value, output_token.length);;
		maj_stat = gss_release_buffer(&min_stat, &output_token);
	}
end:
	if (output_token.value)
		gss_release_buffer(&min_stat, &output_token);

    if (input_token.value)
        gss_release_buffer(&min_stat, &input_token);

	return ret;
}

int authenticate_gss_server_init(const char *service, gss_server_state *state)
{
    OM_uint32 maj_stat;
    OM_uint32 min_stat;
    gss_buffer_desc name_token = GSS_C_EMPTY_BUFFER;
    int ret = AUTH_GSS_COMPLETE;
    
    state->context = GSS_C_NO_CONTEXT;
    state->server_name = GSS_C_NO_NAME;
    state->client_name = GSS_C_NO_NAME;
    state->server_creds = GSS_C_NO_CREDENTIAL;
    state->client_creds = GSS_C_NO_CREDENTIAL;
    state->username = NULL;
    state->targetname = NULL;
    state->response = NULL;
    
    // Server name may be empty which means we aren't going to create our own creds
    size_t service_len = strlen(service);
    if (service_len != 0)
    {
        // Import server name first
        name_token.length = strlen(service);
        name_token.value = (char *)service;
        
        maj_stat = gss_import_name(&min_stat, &name_token, GSS_C_NT_HOSTBASED_SERVICE, &state->server_name);
        
        if (GSS_ERROR(maj_stat))
        {
            set_gss_error(maj_stat, min_stat);
            ret = AUTH_GSS_ERROR;
            goto end;
        }
        
        // Get credentials
        maj_stat = gss_acquire_cred(&min_stat, state->server_name, GSS_C_INDEFINITE,
                                    GSS_C_NO_OID_SET, GSS_C_ACCEPT, &state->server_creds, NULL, NULL);
        
        if (GSS_ERROR(maj_stat))
        {
            set_gss_error(maj_stat, min_stat);
            ret = AUTH_GSS_ERROR;
            goto end;
        }
    }
    
end:
    return ret;
}

int authenticate_gss_server_clean(gss_server_state *state)
{
    OM_uint32 maj_stat;
    OM_uint32 min_stat;
    int ret = AUTH_GSS_COMPLETE;
    
    if (state->context != GSS_C_NO_CONTEXT)
        maj_stat = gss_delete_sec_context(&min_stat, &state->context, GSS_C_NO_BUFFER);
    if (state->server_name != GSS_C_NO_NAME)
        maj_stat = gss_release_name(&min_stat, &state->server_name);
    if (state->client_name != GSS_C_NO_NAME)
        maj_stat = gss_release_name(&min_stat, &state->client_name);
    if (state->server_creds != GSS_C_NO_CREDENTIAL)
        maj_stat = gss_release_cred(&min_stat, &state->server_creds);
    if (state->client_creds != GSS_C_NO_CREDENTIAL)
        maj_stat = gss_release_cred(&min_stat, &state->client_creds);
    if (state->username != NULL)
    {
        free(state->username);
        state->username = NULL;
    }
    if (state->targetname != NULL)
    {
        free(state->targetname);
        state->targetname = NULL;
    }
    if (state->response != NULL)
    {
        free(state->response);
        state->response = NULL;
    }
    
    return ret;
}

int authenticate_gss_server_step(gss_server_state *state, const char *challenge)
{
    OM_uint32 maj_stat;
    OM_uint32 min_stat;
    gss_buffer_desc input_token = GSS_C_EMPTY_BUFFER;
    gss_buffer_desc output_token = GSS_C_EMPTY_BUFFER;
    int ret = AUTH_GSS_CONTINUE;
    
    // Always clear out the old response
    if (state->response != NULL)
    {
        free(state->response);
        state->response = NULL;
    }
    
    // If there is a challenge (data from the server) we need to give it to GSS
    if (challenge && *challenge)
    {
        size_t len;
        input_token.value = base64_decode(challenge, &len);
        input_token.length = len;
    }
    else
    {
        PyErr_SetString(KrbException_class, "No challenge parameter in request from client");
        ret = AUTH_GSS_ERROR;
        goto end;
    }
    
    Py_BEGIN_ALLOW_THREADS
    maj_stat = gss_accept_sec_context(&min_stat,
                                      &state->context,
                                      state->server_creds,
                                      &input_token,
                                      GSS_C_NO_CHANNEL_BINDINGS,
                                      &state->client_name,
                                      NULL,
                                      &output_token,
                                      NULL,
                                      NULL,
                                      &state->client_creds);
    Py_END_ALLOW_THREADS
    
    if (GSS_ERROR(maj_stat))
    {
        set_gss_error(maj_stat, min_stat);
        ret = AUTH_GSS_ERROR;
        goto end;
    }
    
    // Grab the server response to send back to the client
    if (output_token.length)
    {
        state->response = base64_encode((const unsigned char *)output_token.value, output_token.length);;
        maj_stat = gss_release_buffer(&min_stat, &output_token);
    }
    
    // Get the user name
    maj_stat = gss_display_name(&min_stat, state->client_name, &output_token, NULL);
    if (GSS_ERROR(maj_stat))
    {
        set_gss_error(maj_stat, min_stat);
        ret = AUTH_GSS_ERROR;
        goto end;
    }
    state->username = (char *)malloc(output_token.length + 1);
    strncpy(state->username, (char*) output_token.value, output_token.length);
    state->username[output_token.length] = 0;
    
    // Get the target name if no server creds were supplied
    if (state->server_creds == GSS_C_NO_CREDENTIAL)
    {
        gss_name_t target_name = GSS_C_NO_NAME;
        maj_stat = gss_inquire_context(&min_stat, state->context, NULL, &target_name, NULL, NULL, NULL, NULL, NULL);
        if (GSS_ERROR(maj_stat))
        {
            set_gss_error(maj_stat, min_stat);
            ret = AUTH_GSS_ERROR;
            goto end;
        }
        maj_stat = gss_display_name(&min_stat, target_name, &output_token, NULL);
        if (GSS_ERROR(maj_stat))
        {
            set_gss_error(maj_stat, min_stat);
            ret = AUTH_GSS_ERROR;
            goto end;
        }
        state->targetname = (char *)malloc(output_token.length + 1);
        strncpy(state->targetname, (char*) output_token.value, output_token.length);
        state->targetname[output_token.length] = 0;
    }

    ret = AUTH_GSS_COMPLETE;
    
end:
    if (output_token.length)
        gss_release_buffer(&min_stat, &output_token);
    if (input_token.value)
        free(input_token.value);
    return ret;
}


static void set_gss_error(OM_uint32 err_maj, OM_uint32 err_min)
{
    OM_uint32 maj_stat, min_stat;
    OM_uint32 msg_ctx = 0;
    gss_buffer_desc status_string;
    char buf_maj[512];
    char buf_min[512];
    
    do
    {
        maj_stat = gss_display_status (&min_stat,
                                       err_maj,
                                       GSS_C_GSS_CODE,
                                       GSS_C_NO_OID,
                                       &msg_ctx,
                                       &status_string);
        if (GSS_ERROR(maj_stat))
            break;
        strncpy(buf_maj, (char*) status_string.value, sizeof(buf_maj));
        gss_release_buffer(&min_stat, &status_string);
        
        maj_stat = gss_display_status (&min_stat,
                                       err_min,
                                       GSS_C_MECH_CODE,
                                       GSS_C_NULL_OID,
                                       &msg_ctx,
                                       &status_string);
        if (!GSS_ERROR(maj_stat))
        {
            strncpy(buf_min, (char*) status_string.value, sizeof(buf_min));
            gss_release_buffer(&min_stat, &status_string);
        }
    } while (!GSS_ERROR(maj_stat) && msg_ctx != 0);
    
    PyErr_SetObject(GssException_class, Py_BuildValue("((s:i)(s:i))", buf_maj, err_maj, buf_min, err_min));
}
