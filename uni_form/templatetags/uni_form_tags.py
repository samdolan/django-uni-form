from django.conf import settings
from django.template import Context, Template
from django.forms.formsets import BaseFormSet
from django.template.loader import get_template
from django import template

from django.template.defaultfilters import slugify

register = template.Library()


###################################################
# Core as_uni_form filter.
# You will likely use this simple filter
# most of the time.
# This is easy to get working and very simple in
# concept and execution.
###################################################
@register.filter
def as_uni_form(form):
    template = get_template('uni_form/uni_form.html')
    c = Context({'form':form})
    return template.render(c)

@register.filter
def as_uni_form_set(formset):
    template = get_template('uni_form/uni_form_set.html')
    c = Context({'formset':formset})
    return template.render(c)

@register.filter
def as_uni_errors(form):
    template = get_template('uni_form/errors.html')
    c = Context({'form':form})
    return template.render(c)

@register.filter
def as_uni_field(field):
    template = get_template('uni_form/field.html')
    c = Context({'field':field})
    return template.render(c)
    
@register.inclusion_tag("uni_form/includes.html", takes_context=True)
def uni_form_setup(context):
    """
Creates the <style> and <script> tags needed to initialize the uni-form.
 
Create a local uni-form/includes.html template if you want to customize how
these files are loaded. 
"""
    if 'MEDIA_URL' not in context:
        context['MEDIA_URL'] = settings.MEDIA_URL        
    return (context)

############################################################################
#
# Everything from now on gets more fancy
# It can be argued that having django-uni-form construct your forms is overkill
# and that I am playing architecture astronaut games with form building.
#
# However, all the bits that follow are designed to be section 508 compliant,
# so all the fancy JS bits are garanteed to degrade gracefully.
#
############################################################################

def namify(text):
    """ Some of our values need to be rendered safe as python variable names.
        So we just replaces hyphens with underscores.
    """
    return slugify(text).replace('-','_')
    

class HelperHandlerNode(template.Node):
    """Base class for form and formset nodes

    This base class provides the ability to extract attributes from a helper
    into a template context.  This is shared by all uni-form node types.
    """
    def __init__(self, helper):
        self.helper = template.Variable(helper)

    def get_render(self, context):
        helper = self.helper.resolve(context)
        attrs = {}
        if helper:
            attrs = helper.get_attr()
        response_dict = self.get_response_context(context, helper, attrs)
        return Context(response_dict)

    def get_response_context(self, context, helper, helper_attrs):
        """Extract attributes from a helper or use default values

        Attributes:
         * context: the current template context
         * helper: the uni-form helper object or None if none provided
         * helper_attrs: a dict of attributes extracted from the helper object,
                         or an empty dict if no helper provided

        Return value: a dictionary to be inserted in the context when rendering
                      the form/formset

        Override this method to provide extra attributes for helpers.
        """
        form_method = helper_attrs.get("form_method", 'POST')
        form_action = helper_attrs.get("form_action", '')
        form_class = helper_attrs.get("class", '')
        form_id = helper_attrs.get("id", "")
        inputs = helper_attrs.get('inputs', [])

        return {'form_action': form_action,
                'form_method': form_method,
                'attrs': helper_attrs,
                'form_class': form_class,
                'form_id': form_id,
                'inputs': inputs}


class BasicNode(HelperHandlerNode):
    """ Basic Node object that we can rely on for Node objects in normal
        template tags. I created this because most of the tags we'll be using
        will need both the form object and the helper string. This handles
        both the form object and parses out the helper string into attributes
        that templates can easily handle. """
    
    def __init__(self, form, helper):
        self.form = template.Variable(form)
        HelperHandlerNode.__init__(self, helper)

    def get_response_context(self, context, helper, helper_attrs):
        actual_form = self.form.resolve(context)
        toggle_fields = helper_attrs.get('toggle_fields', set(()))
        final_toggle_fields = []
        if toggle_fields:
            final_toggle_fields = []
            for field in actual_form:
                if field.auto_id in toggle_fields:
                    final_toggle_fields.append(field)

        response_dict = super(BasicNode, self).get_response_context(
            context, helper, helper_attrs)
        response_dict['form'] = actual_form
        response_dict['toggle_fields'] = final_toggle_fields
        if helper and helper.layout:
            form_html = helper.render_layout(actual_form)
        else:
            form_html = ""
        response_dict['form_html'] = form_html
        return response_dict

class BasicFormsetNode(HelperHandlerNode):
    """Base class for formset template tag nodes

    This base class extends the helper attributes handler by:
     * storing the formset in context['formset']
     * rendering all subforms with the helper's layout if available
    """
    def __init__(self, formset, helper):
        self.formset = template.Variable(formset)
        HelperHandlerNode.__init__(self, helper)

    def get_response_context(self, context, helper, helper_attrs):
        if 'toggle_fields' in helper_attrs:
            raise NotImplementedError(
                "'toggle_fields' not yet supported for formsets")
        actual_formset = self.formset.resolve(context)
        response_dict = super(BasicFormsetNode, self).get_response_context(
            context, helper, helper_attrs)
        response_dict['formset'] = actual_formset
        if helper and helper.layout:
            for form in actual_formset.forms:
                form.form_html = helper.render_layout(form)
        return response_dict


##################################################################
#
# Actual tags start here
#
##################################################################


@register.tag(name="uni_form")
def do_uni_form(parser, token):
    
    """
    You need to pass in at least the form object, and can also pass in the
    optional attrs string. Writing the attrs string is rather challenging so
    use of the objects found in uni_form.helpers is encouraged.
    
    form: The forms object to be rendered by the tag
    
    attrs (optional): A string of semi-colon seperated attributes that can be
    applied to theform in string format. They are used as follows.
    
    form_action: applied to the form action attribute. Can be a named url in 
    your urlconf that can be executed via the *url* default template tag or can
    simply point to another URL. 
    Defaults to empty::
        
        form_action=<my-form-action>
    
    form_method: applied to the form action attribute. Defaults to POST and the only available thing you can enter is GET.::
        
        form_method=<my-form-method>
    
    id: applied to the form as a whole. Defaults to empty::
        
        id=<my-form-id>
    
    class: add space seperated classes to the class list. Always starts with uniform::
        
        class=<my-first-custom-form-class> <my-custom-form-class>
    
    button: for adding of generic buttons. The name also becomes the slugified id::
        
        button=<my-custom-button-name>|<my-custom-button-value>
    
    submit: For adding of submt buttons. The name also becomes the slugified id::
        
        submit=<my-custom-submit-name>|<my-custom-submit-value>
    
    hidden: For adding of hidden buttons::
        
        hidden=<my-custom-hidden-name>|<my-custom-hidden-value>
    
    reset: For adding of reset buttons::
        
        reset=<my-custom-reset-name>|<my-custom-reset-value>

    
    Example::
        
        {% uni_form my-form my_helper %}
    
    """
    
    token = token.split_contents()
    
    form = token.pop(1)
    try:
        helper = token.pop(1)
    except IndexError:
        helper = None

    
    return UniFormNode(form, helper)
    

class UniFormNode(BasicNode):
    
    def render(self, context):
        
        c = self.get_render(context)
        
        template = get_template('uni_form/whole_uni_form.html')
        return template.render(c)


@register.tag(name="uni_form_set")
def do_uni_form_set(parser, token):

    """
    You need to pass in at least the formset object, and can also pass in the
    optional helper object (see :module:`uni_form.helpers`).

    Example::

        {% uni_form_set my-formset my_helper %}

    """

    token = token.split_contents()

    formset = token.pop(1)
    try:
        helper = token.pop(1)
    except IndexError:
        helper = None

    return UniFormsetNode(formset, helper)


class UniFormsetNode(BasicFormsetNode):

    def render(self, context):

        c = self.get_render(context)

        template = get_template('uni_form/whole_uni_form_set.html')
        return template.render(c)


#################################
# uni_form scripts
#################################

@register.tag(name="uni_form_jquery")
def uni_form_jquery(parser, token):
    """
    toggle_field: For making fields designed to be toggled for editing add them
    by spaces. You must specify by field id (field.auto_id)::
        
        toggle_fields=<first_field>,<second_field>
    
    """
    
    token = token.split_contents()
    
    form = token.pop(1)
    try:
        attrs = token.pop(1)
    except IndexError:
        attrs = None

    
    return UniFormJqueryNode(form,attrs)

class UniFormJqueryNode(BasicNode):
    
    def render(self,context):
        
        c = self.get_render(context)
        
        template = get_template('uni_form/uni_form_jquery.html')
        return template.render(c)   
